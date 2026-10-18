"""Idempotent, exact-identifier insurance upload with read-back/hash/audit checks."""
import argparse,json,hashlib
from pathlib import Path
from urllib.parse import quote
from document_access import Client,ApiError,request,BASE

def run(folder,limit,expected_count=63,expected_pages=74):
    manifest=json.loads((folder/'upload manifest.json').read_text())
    ready=[x for x in manifest if x['ready']]
    assert len(ready)==expected_count and len(manifest)==expected_pages and expected_count>0
    c=Client();assets=c.assets();byid={a['id']:a for a in assets}
    reportpath=folder/'upload results.json'
    results=json.loads(reportpath.read_text()) if reportpath.exists() else []
    done={r['sha256']:r for r in results}
    work=ready[:limit] if limit else ready
    for x in work:
        m=x['metadata'];blob=Path(x['local_pdf']).read_bytes()
        assert hashlib.sha256(blob).hexdigest()==m['sha256'] and len(blob)==m['byte_size']
        assert byid[m['asset_id']]['vin']==m['source_identifier']
        assert sum(a.get('vin')==m['source_identifier'] for a in assets)==1
        query='/rest/v1/asset_documents?asset_id=eq.'+m['asset_id']+'&sha256=eq.'+m['sha256']
        existing=c.call(query)
        path='/storage/v1/object/asset-documents/'+quote(m['storage_path'],safe='/')
        if not existing:
            try:c.call(path,'POST',raw=blob,extra={'Content-Type':'application/pdf','x-upsert':'false'})
            except ApiError as e:
                if not (e.status==409 or (e.status==400 and getattr(e,'api_code','') in ('Duplicate','ResourceAlreadyExists','KeyAlreadyExists'))):raise
                # A deterministic existing path is never overwritten. Metadata/readback below must verify it.
            c.call('/rest/v1/asset_documents','POST',payload=m,extra={'Prefer':'return=representation'})
        readback=c.call(query)
        assert len(readback)==1
        r=readback[0]
        for key,value in m.items():assert r[key]==value,(key,'metadata mismatch')
        downloaded=c.call('/storage/v1/object/authenticated/asset-documents/'+quote(m['storage_path'],safe='/'))
        assert isinstance(downloaded,bytes) and hashlib.sha256(downloaded).hexdigest()==m['sha256']
        audit=c.call('/rest/v1/asset_document_history?document_id=eq.'+r['id'])
        assert len(audit)==1 and audit[0]['op']=='UPLOAD' and audit[0]['actor_id']==c.user['id'] and audit[0]['changes']['sha256']==m['sha256']
        assert audit[0]['asset_id']==m['asset_id']
        done[m['sha256']]={'document_id':r['id'],'asset_id':m['asset_id'],'sha256':m['sha256'],'original_name':m['original_name'],'metadata_verified':True,'download_sha256_verified':True,'audit_verified':True}
        reportpath.write_text(json.dumps(list(done.values()),indent=2),encoding='utf-8')
    first=work[0]['metadata']
    try:
        request(BASE+'/storage/v1/object/public/asset-documents/'+quote(first['storage_path'],safe='/'))
        raise AssertionError('Private document unexpectedly public')
    except ApiError as e:
        assert e.status in (400,401,403,404)
    print(json.dumps({'verified_documents':len(done),'unique_assets':len({r['asset_id'] for r in done.values()}),'public_download_denied':True,'scope_total':len(ready),'remaining':len(ready)-len(done)}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--limit',type=int);a=p.parse_args();run(a.folder,a.limit)
