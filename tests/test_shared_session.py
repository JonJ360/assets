"""Same-origin session import with synthetic storage and network-blocked Edge."""
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
KEY='sb-inhwadbibwkakacdvoxu-auth-token'

@pytest.fixture(params=['index.html','irp.html'])
def session_page(request):
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page()
        page.route('**/*',lambda route:route.abort())
        page.set_content((ROOT/request.param).read_text(encoding='utf-8'))
        page.evaluate("""() => {
          const values={}; window.store=values;
          Object.defineProperty(window,'localStorage',{value:{getItem:k=>values[k]||null,setItem:(k,v)=>values[k]=v,removeItem:k=>delete values[k]}});
          window.requests=[];
          fetch=async(url,opt)=>{ requests.push({url,...opt});return new Response(JSON.stringify({id:'verified-id',email:'viewer@example.invalid'}),{status:window.rejectSession?401:200}); };
          AUTH.s=null;
        }""")
        yield page
        browser.close()

@pytest.mark.parametrize('legacy',['absent','expired'])
def test_verified_sdk_import_without_password(session_page,legacy):
    page=session_page
    page.evaluate("""({key,legacy})=>{
      store[key]=JSON.stringify({access_token:'sdk-synthetic',refresh_token:'refresh-synthetic',expires_at:Date.now()/1000+3600,user:{email:'jonj@360-llc.com'}});
      if(legacy==='expired') AUTH.s={access_token:'old',exp:1,email:'old@example.invalid'};
    }""",dict(key=KEY,legacy=legacy))
    assert page.evaluate('AUTH.token()')=='sdk-synthetic'
    assert page.evaluate('AUTH.email()')=='viewer@example.invalid'
    assert page.evaluate('AUTH.isEditor()') is False
    requests=page.evaluate('requests')
    assert len(requests)==1 and requests[0]['url'].endswith('/auth/v1/user')
    assert requests[0]['headers']['Authorization']=='Bearer sdk-synthetic'
    assert page.evaluate("JSON.parse(store['assets-auth-v1']).email")=='viewer@example.invalid'

@pytest.mark.parametrize('mode',['missing','malformed','expired','rejected'])
def test_invalid_sdk_keeps_fresh_signin(session_page,mode):
    page=session_page
    page.evaluate("""({key,mode})=>{
      if(mode==='malformed')store[key]='not-json';
      else if(mode!=='missing')store[key]=JSON.stringify({access_token:'sdk-synthetic',refresh_token:'refresh-synthetic',expires_at:mode==='expired'?1:Date.now()/1000+3600});
      window.rejectSession=mode==='rejected';
    }""",dict(key=KEY,mode=mode))
    assert page.evaluate('AUTH.token()') is None
    assert page.evaluate('AUTH.s') is None
    assert page.evaluate("store['assets-auth-v1']||null") is None
    assert all('/auth/v1/user' in c['url'] for c in page.evaluate('requests'))

def test_valid_legacy_is_preserved(session_page):
    page=session_page
    page.evaluate("AUTH.s={email:'viewer@example.invalid',access_token:'legacy',exp:Date.now()+3600000}")
    assert page.evaluate('AUTH.token()')=='legacy'
    assert page.evaluate('requests')==[]

def test_signout_cannot_reimport_shared_session(session_page):
    page=session_page
    page.evaluate("key=>{store[key]=JSON.stringify({access_token:'sdk-synthetic',refresh_token:'r',expires_at:Date.now()/1000+3600});AUTH.signOut();}",KEY)
    assert page.evaluate('AUTH.token()') is None
    assert page.evaluate('requests')==[]

@pytest.mark.parametrize('filename',['index.html','irp.html'])
@pytest.mark.parametrize('shared',[True,False])
def test_boot_reuses_verified_hub_or_shows_signin(filename,shared):
    import json
    setup="""<script>
      const fixtureStore={};
      Object.defineProperty(window,'localStorage',{value:{getItem:k=>fixtureStore[k]||null,setItem:(k,v)=>fixtureStore[k]=v,removeItem:k=>delete fixtureStore[k]}});
      window.bootCalls=[];
      window.fetch=async(url,opt)=>{bootCalls.push(url);return new Response(JSON.stringify(url.endsWith('/auth/v1/user')?{id:'verified',email:'viewer@example.invalid'}:[]),{status:200});};
    """
    if shared:
        setup+="fixtureStore["+json.dumps(KEY)+"]=JSON.stringify({access_token:'fixture',refresh_token:'fixture-refresh',expires_at:Date.now()/1000+3600});"
    setup+='</script>'
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page()
        page.route('**/*',lambda route:route.abort())
        page.set_content(setup+(ROOT/filename).read_text(encoding='utf-8'))
        if shared:
            page.wait_for_function("bootCalls.some(url=>url.includes('/rest/v1/assets'))")
            assert page.evaluate('AUTH.email()')=='viewer@example.invalid'
            assert page.locator('#loginBox').is_hidden()
            assert page.evaluate('bootCalls[0]').endswith('/auth/v1/user')
        else:
            page.wait_for_function("document.querySelector('#loginBox').style.display==='block'")
            assert page.evaluate('bootCalls')==[]
        browser.close()
