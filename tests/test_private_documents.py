"""Synthetic private-document checks; Edge network is blocked throughout."""
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ASSET = '11111111-1111-4111-8111-111111111111'
DOC = dict(id='22222222-2222-4222-8222-222222222222', asset_id=ASSET,
           document_type='insurance', status='active', storage_bucket='asset-documents',
           storage_path=ASSET+'/card #1.pdf', original_name='Insurance.pdf',
           mime_type='application/pdf', policy_number='POL-TEST',
           effective_date='2020-01-01', expiration_date='2021-01-01')

@pytest.fixture(params=['index.html', 'irp.html'])
def app(request):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page()
        page.route('**/*', lambda route: route.abort())
        page.set_content((ROOT/request.param).read_text(encoding='utf-8'))
        page.add_style_tag(content='*, *::before, *::after { transition: none !important; animation: none !important; }')
        page.evaluate("""({asset, portal}) => {
          hideLogin(); AUTH.s={email:'viewer@example.invalid'};
          window.docRows=[]; window.docCalls=[];
          sb=async(path,opt)=>{if(path.startsWith('asset_documents?')){
            docCalls.push(path); if(window.failDocs) throw Error('private backend detail'); return docRows;
          } return [];};
          const row={id:asset,name:'Synthetic vehicle',status:'Active',doc_url:'https://example.invalid/legacy'};
          window.openFixture=()=>{if(portal){ROWS=[row];open(asset);}else{state.assets=[row];openAsset(asset);}};
        }""", dict(asset=ASSET, portal=request.param=='irp.html'))
        yield page
        browser.close()

def test_empty_list_is_asset_scoped(app):
    app.evaluate('openFixture()')
    expect(app.locator('#assetDocuments')).to_contain_text('No insurance documents')
    calls = app.evaluate('docCalls')
    assert len(calls)==1
    assert 'asset_id=eq.'+ASSET in calls[0]
    assert 'status=eq.active' in calls[0]
    assert 'document_type=eq.insurance' in calls[0]

def test_list_error_is_not_empty_or_backend_detail(app):
    app.evaluate('failDocs=true;openFixture()')
    expect(app.locator('#assetDocuments')).to_contain_text('unavailable')
    assert 'private backend detail' not in app.locator('#assetDocuments').inner_text()

def test_escaping_dates_and_defensive_filter(app):
    dangerous = '<img src=x onerror="window.injected=true">'
    app.evaluate('rows=>{docRows=rows;openFixture()}', [
        dict(DOC, original_name=dangerous, policy_number=dangerous),
        dict(DOC, asset_id='other', original_name='WRONG ASSET'),
        dict(DOC, status='archived', original_name='ARCHIVED'),
        dict(DOC, document_type='title', original_name='TITLE')])
    host=app.locator('#assetDocuments')
    expect(host).to_contain_text(dangerous)
    assert host.locator('img').count()==0
    assert host.locator('button').all_text_contents()==['Open','Download']
    for text in ['Insurance ID Card','2020-01-01','2021-01-01','Expired']:
        expect(host).to_contain_text(text)
    assert 'WRONG ASSET' not in host.inner_text()
    assert 'ARCHIVED' not in host.inner_text()

def setup_download(app):
    app.evaluate('rows=>{docRows=rows;openFixture()}', [DOC])
    app.evaluate("""() => {
      AUTH.token=async()=> 'synthetic-token'; window.fetchCalls=[]; window.links=[];
      window.revoked=[]; window.delays=[];
      window.fetch=async(url,opt)=>{fetchCalls.push({url, ...opt}); return new Response('%PDF-1.4 synthetic', {status:window.downloadStatus||200,headers:{'Content-Type':'application/pdf'}});};
      URL.createObjectURL=blob=>{window.blobType=blob.type;return 'blob:synthetic';};
      URL.revokeObjectURL=url=>revoked.push(url);
      window.setTimeout=(fn,ms)=>{delays.push(ms);window.cleanup=fn;return 1;};
      HTMLAnchorElement.prototype.click=function(){links.push({href:this.href,download:this.download,target:this.target,rel:this.rel});};
    }""")

@pytest.mark.parametrize('action', ['Open','Download'])
def test_authenticated_blob_actions(app, action):
    setup_download(app)
    app.get_by_role('button',name=action,exact=True).click()
    app.wait_for_function('links.length===1')
    result=app.evaluate('({fetchCalls,links,revoked,delays,blobType})')
    call=result['fetchCalls'][0]
    assert call['url'].endswith('/storage/v1/object/authenticated/asset-documents/'+ASSET+'/card%20%231.pdf')
    assert call['headers']['Authorization']=='Bearer synthetic-token'
    assert call['headers']['apikey'].startswith('sb_publishable_')
    assert call['cache']=='no-store'
    assert result['links'][0]['href']=='blob:synthetic'
    assert result['blobType']=='application/pdf'
    assert result['revoked']==[] and max(result['delays'])>=60000
    if action=='Download': assert result['links'][0]['download']=='Insurance.pdf'
    else: assert result['links'][0]['target']=='_blank' and 'noopener' in result['links'][0]['rel']
    app.evaluate('cleanup()')
    assert app.evaluate('revoked')==['blob:synthetic']

@pytest.mark.parametrize('failure', ['signed-out','http'])
def test_download_failure_no_blob_or_token_disclosure(app,failure):
    setup_download(app)
    app.evaluate("AUTH.token=async()=>null" if failure=='signed-out' else 'downloadStatus=403')
    app.get_by_role('button',name='Download',exact=True).click()
    expect(app.locator('#assetDocuments')).to_contain_text('Unable to retrieve document')
    assert app.evaluate('links')==[]
    if failure=='signed-out': assert app.evaluate('fetchCalls')==[]
    assert 'synthetic-token' not in app.locator('#assetDocuments').inner_text()

def test_late_asset_response_cannot_replace_current_list(app):
    app.evaluate("""() => {
      window.resolveOld=null;
      sb=path=>path.startsWith('asset_documents?')?new Promise(resolve=>resolveOld=resolve):Promise.resolve([]);
      openFixture();
      sb=async()=>[];
      openFixture();
    }""")
    app.evaluate('row=>resolveOld([row])',DOC)
    expect(app.locator('#assetDocuments')).to_contain_text('No insurance documents')

@pytest.mark.parametrize('field,value',[('storage_bucket','public'),('storage_path','../secret.pdf'),('mime_type','text/html')])
def test_invalid_metadata_cannot_fetch_objects(app,field,value):
    setup_download(app)
    app.evaluate('row=>{docRows=[row];openFixture()}',dict(DOC,**{field:value}))
    app.get_by_role('button',name='Download',exact=True).click()
    expect(app.locator('#assetDocuments')).to_contain_text('Unable to retrieve document')
    assert app.evaluate('fetchCalls')==[]

def test_legacy_document_url_preserved_and_mobile_list_fits(app):
    app.set_viewport_size({'width':390,'height':844})
    app.evaluate('rows=>{docRows=rows;openFixture()}',[dict(DOC,original_name='x'*150+'.pdf')])
    host=app.locator('#assetDocuments')
    expect(host).to_contain_text('Insurance ID Card')
    box=host.bounding_box()
    assert box and box['x']>=0 and box['x']+box['width']<=390
    if app.locator('#f_doc_url').count():
        assert app.locator('#f_doc_url').input_value()=='https://example.invalid/legacy'
