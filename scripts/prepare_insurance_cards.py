"""Prepare individual original-page insurance cards with exact identity matching."""
import argparse,json,re,hashlib
from pathlib import Path
from datetime import datetime
import pymupdf

def prepare(root):
    rows=json.loads((root/'source pages.json').read_text())
    assets=json.loads((root/'live assets.json').read_text())
    manifest=[]
    for row in rows:
        lines=[x.strip() for x in row['text'].splitlines()]
        dates=re.findall(r'\b\d{2}/\d{2}/\d{4}\b',row['text'])
        assert len(dates)==2
        policy=lines[lines.index(dates[0])-1]
        matches=[a for a in assets if a.get('vin') and a['vin'] in lines]
        a=matches[0] if len(matches)==1 else None
        valid=a is not None and (re.fullmatch('[A-HJ-NPR-Z0-9]{17}',a['vin']) or a['vin'] in ('3X5229','445473'))
        identifier=a['vin'] if a else (row['vin_candidates'][0] if len(row['vin_candidates'])==1 else 'Unresolved')
        note=''
        if a and not valid:note='Exact register token is malformed for a modern VIN; held without correction'
        elif not a:note='No unique exact identifier match in register'
        elif row['entity']!=a['entity']:note='Insured entity differs from registered asset entity; exact identifier match; source preserved'
        label=(str(a.get('unit_no') or '')+' '+a['name']).strip() if a else 'Source page '+str(row['page'])
        label=re.sub(r'[<>:"/\\|?*]',' ',label)
        filename=f"{row['entity']} {label} {identifier} Insurance ID {dates[0][-4:]} - {policy}.pdf"
        folder=root/('Ready' if valid else 'Needs review');folder.mkdir(exist_ok=True)
        path=folder/filename
        with pymupdf.open(row['source']) as src:
            dst=pymupdf.open();dst.insert_pdf(src,from_page=row['page']-1,to_page=row['page']-1)
            blob=dst.tobytes(garbage=4,deflate=True,no_new_id=True);dst.close()
            path.write_bytes(blob)
            with pymupdf.open(path) as check:
                assert len(check)==1 and check[0].get_text()==src[row['page']-1].get_text()
                # Pixel equality proves the standalone PDF preserves the entire card.
                assert check[0].get_pixmap().samples==src[row['page']-1].get_pixmap().samples
        sha=hashlib.sha256(blob).hexdigest()
        meta=dict(asset_id=a['id'] if valid else None,document_type='insurance',storage_bucket='asset-documents',storage_path=f"{a['id']}/insurance/{sha}.pdf" if valid else None,original_name=filename,mime_type='application/pdf',byte_size=len(blob),sha256=sha,policy_number=policy,effective_date=datetime.strptime(dates[0],'%m/%d/%Y').date().isoformat(),expiration_date=datetime.strptime(dates[1],'%m/%d/%Y').date().isoformat(),insured_entity=row['entity'],source_identifier=identifier,status='active')
        manifest.append(dict(source=row['source'],source_page=row['page'],local_pdf=str(path),ready=bool(valid),note=note,metadata=meta))
    assert len(manifest)==len(rows)==74
    keys=[(x['metadata']['asset_id'],x['metadata']['sha256']) for x in manifest if x['ready']]
    assert len(keys)==len(set(keys))
    (root/'upload manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    import csv
    with (root/'Insurance Card Reconciliation.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=['insured_entity','source_page','identifier','ready','asset_id','policy','note','file']);w.writeheader()
        for x in manifest:w.writerow(dict(insured_entity=x['metadata']['insured_entity'],source_page=x['source_page'],identifier=x['metadata']['source_identifier'],ready=x['ready'],asset_id=x['metadata']['asset_id'],policy=x['metadata']['policy_number'],note=x['note'],file=x['local_pdf']))
    print(json.dumps({'source_pages':len(rows),'pdfs_verified_text_and_pixels':len(manifest),'ready':sum(x['ready'] for x in manifest),'held':sum(not x['ready'] for x in manifest),'unique_assets':len({k[0] for k in keys})}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);prepare(p.parse_args().folder)
