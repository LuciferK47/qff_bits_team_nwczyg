"""Version 2 of the independent audit checker (the original is kept unchanged in the audit folder). Accepts the supplementary
verification ledger and the corrected log pointer; output directory is the second argument. Usage: python independent_checks_v2.py REPO OUTDIR
Independent, no-Qiskit verification of frozen experimental evidence and the release.
Requires pandas and numpy for table reconstruction. Does not submit quantum jobs.
Usage: python independent_checks.py [path_to_repo_root]
"""
from pathlib import Path
import csv, hashlib, json, zipfile, collections, sys, re
import numpy as np
import pandas as pd
ROOT=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
OUT=Path(sys.argv[2] if len(sys.argv)>2 else '.').resolve(); OUT.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
records=[]
def check(name, ok, detail=''):
    records.append({'check':name,'result':'PASS' if ok else 'FAIL','detail':str(detail)})

evidence=pd.read_csv(ROOT/'reports/evidence_hashes.csv')
bad=[str(row.path) for row in evidence.itertuples() if not (ROOT/row.path).is_file() or sha(ROOT/row.path)!=row.sha256]
check('frozen_evidence_ledger',not bad,f'{len(evidence)} records; mismatches={bad[:8]}')
all_account_files={p.relative_to(ROOT).as_posix() for a in (1,2) for p in (ROOT/f'raw/hardware/account{a}').rglob('*') if p.is_file()}
supp=pd.read_csv(ROOT/'reports/job_verification_hashes.csv')
bad_supp=[str(r.path) for r in supp.itertuples() if sha(ROOT/r.path)!=r.sha256]
check('supplementary_ledger_hashes',not bad_supp and len(supp)==2,f'{len(supp)} records; mismatches={bad_supp}')
check('original_ledger_still_68',len(evidence)==68,f'{len(evidence)} records')
unlisted=all_account_files-set(evidence.path)-set(supp.path)
check('ledger_covers_all_hardware_account_files',not unlisted, f'{len(all_account_files)} account files; unlisted={sorted(unlisted)}')
prereg=json.loads((ROOT/'prereg/prereg.json').read_text())
prereg_bad=[x for x, h in prereg['files'].items() if not (ROOT/x).is_file() or sha(ROOT/x)!=h]
check('prereg_file_hashes',not prereg_bad,f'{len(prereg["files"])} files; mismatches={prereg_bad}')
approval=(ROOT/'prereg/APPROVAL.md').read_text()
check('prereg_approval_hash',prereg['prereg_sha'] in approval,f'sha={prereg["prereg_sha"]}')

jobs=[]; execution=[]; verif=[]; qpy_errors=[]; times=[]
for a in (1,2):
  d=ROOT/f'raw/hardware/account{a}'; jobmap=json.loads((d/'jobs.json').read_text()); live=json.loads((d/'live_check.json').read_text()); verify=json.loads((d/'job_verification.json').read_text()); metas={m['label']:m for group in live['jobs'].values() for m in group}
  for name, job in jobmap.items():
    raw=json.loads((d/f'{name}_results.json').read_text()); remote=verify['jobs'][name]
    tot=0
    for label, counts in raw['counts'].items():
      s=sum(counts.values());tot+=s
      spec=metas[label]; qpy=d/f'circuits/{label}.qpy'; digest=sha(qpy)
      ok=digest.startswith(spec['qpy_sha']) and s==spec['shots'] and spec['depth_2q']<=300
      if not ok:qpy_errors.append((a,label,s,spec['shots'],spec['depth_2q'],digest[:16],spec['qpy_sha']))
      execution.append((a,name,label,s,spec['depth_2q'],spec.get('n_2q', spec.get('compiled_2q_count', None))))
    ok=raw['job_id']==job['job_id']==remote['job_id'] and raw['backend']==job['backend']==remote['ibm_backend']=='ibm_fez' and raw['usage_s']==remote['ibm_usage_s'] and remote['ibm_status']=='DONE' and remote['found'] and remote['usage_matches'] and remote['backend_matches'] and set(job['labels'])==set(raw['counts'])
    verif.append(ok)
    jobs.append({'account':a,'job':name,'job_id':job['job_id'],'shots':tot,'usage_s':raw['usage_s'],'estimated_s':job['estimated_s'],'remote_record_matches':ok})
    times.append(job['submitted_utc'])
check('six_job_counts_usages',len(jobs)==6 and len(execution)==56 and sum(x['shots'] for x in jobs)==720896 and sum(x['usage_s'] for x in jobs)==202.0 and all(verif), f"jobs={len(jobs)},circuits={len(execution)},shots={sum(x['shots'] for x in jobs)},usage={sum(x['usage_s'] for x in jobs)}")
check('circuit_hashes_counts_depth',not qpy_errors, f'{len(execution)} saved QPY / counts / depths verified; problems={qpy_errors[:3]}')
check('chronological_prereg',min(times) > prereg['created_utc'],f'prereg={prereg["created_utc"]}; first_job={min(times)}')

res=pd.read_csv(ROOT/'results.csv');hw=pd.read_csv(ROOT/'raw/hardware/hardware_results.csv');resources=pd.read_csv(ROOT/'resources.csv');d=pd.read_csv(ROOT/'raw/hardware/drift_account2_vs_1.csv');meta=json.loads((ROOT/'metadata.json').read_text()); hwexp=res[res.source=='hardware'].copy()
check('summary_counts',len(res)==15108 and len(hw)==4230 and len(hwexp)==4230 and len(d)==2115 and len(resources)==121,f'results={len(res)},hardware={len(hw)},drift={len(d)},resources={len(resources)}')
indices=hwexp.notes.fillna('').str.extract(r'source_row=(\d+)$')[0]
ok_index=indices.notna().all() and sorted(indices.astype(int))==list(range(len(hw)))
check('source_row_provenance',ok_index,'all 4230 hardware export rows map to unique raw hardware rows')
if ok_index:
  mapped=hw.loc[indices.astype(int).to_numpy()].reset_index(drop=True); out=hwexp.reset_index(drop=True)
  cols=[('graph_id','graph_id'),('N','N'),('observable','observable'),('method','method'),('estimate','estimate'),('ci_low','ci_low'),('ci_high','ci_high'),('reference','reference'),('validation_status','trust_status')]
  differences=[]
  for x,y in cols:
    if x in ('estimate','ci_low','ci_high','reference'):
      ok=np.allclose(out[x],mapped[y],atol=1e-10,rtol=0,equal_nan=True)
    else:ok=(out[x].fillna('MISSING').astype(str).to_numpy()==mapped[y].fillna('MISSING').astype(str).to_numpy()).all()
    if not ok:differences.append(x)
  check('raw_to_export_hardware_values',not differences,f'check columns={len(cols)},differences={differences}')

by1=hw[hw.account==1];by2=hw[hw.account==2]
keys=['graph_id','N','method','observable','sites']
joined=by1.merge(by2,on=keys,suffixes=('_1','_2'))
se=np.sqrt(joined.se_1.to_numpy()**2+joined.se_2.to_numpy()**2)
z=(joined.estimate_1.to_numpy()-joined.estimate_2.to_numpy())/np.where(se>0,se,np.nan)
flags=np.abs(z)>4
joined['drift_z_check']=z;joined['drift_flag_check']=flags
j=joined.merge(d,on=keys,validate='one_to_one')
match_z=np.allclose(j['drift_z_check'],j['drift_z'],atol=1e-10,rtol=0,equal_nan=True)
match_flag=(j['drift_flag_check']==j['drift_flag']).all()
check('recompute_drift_from_hardware_table',len(joined)==len(d)==2115 and match_z and match_flag and flags.sum()==650,f'count={len(j)},flags={flags.sum()},maxerr={np.nanmax(np.abs(j.drift_z_check-j.drift_z)):.3g}')

status=hw.trust_status.value_counts(dropna=False).to_dict(); invalid_no_ref=hw[(~np.isfinite(hw.estimate))&(hw.trust_status=='no_reference')]
check('no_nonfinite_supported',not ((~np.isfinite(hw.estimate)) & (hw.trust_status.isin(['supported','inconsistent']))).any(),f'nonfinite_no_reference={len(invalid_no_ref)}, all_nonfinite={int((~np.isfinite(hw.estimate)).sum())}')

meta_hw=meta['hardware'];check('metadata_hardware_agrees',meta_hw['n_jobs']==6 and meta_hw['n_executions']==56 and meta_hw['total_shots']==720896 and meta_hw['total_reported_usage_s']==202 and len(meta['job_ids'])==6,'six jobs, 56 circuits, 720896 shots, 202s')

with zipfile.ZipFile(ROOT/'dist/TEAM-NWCZYG.zip') as z:
 files=z.namelist();mismatch=[]
 for f in files:
  p=ROOT/f
  if p.is_file():
    orig=p.read_bytes();arch=z.read(f)
    if orig!=arch and not f.endswith('.log'):mismatch.append(f)
 prohibited=[f for f in files if '/.venv/' in f or f.startswith('.venv/') or f.startswith('.git/') or '/.git/' in f or f.endswith('.env')]
 req=['README.md','requirements.lock','results.csv','resources.csv','metadata.json']
 check('release_archive_equals_current_nonlog_source',not mismatch,f'{len(files)} entries; non-log mismatch={mismatch}')
 check('release_archive_required_and_clean',not prohibited and all(x in files for x in req) and any(x.startswith('raw/') for x in files) and any(x.startswith('src/') for x in files),f'prohibited={prohibited[:5]}; required={req}')
  
check('reproducibility_doc_points_to_latest_log', 'logs/verify_release3.log' in (ROOT/'reports/REPRODUCIBILITY.md').read_text(), 'REPRODUCIBILITY.md must name logs/verify_release3.log or later')

pd.DataFrame(records).to_csv(OUT/'independent_verification_checks.csv',index=False)
pd.DataFrame(jobs).to_csv(OUT/'job_reconciliation.csv',index=False)
summary={'checks':collections.Counter(x['result'] for x in records),'shot_totals':sum(x['shots'] for x in jobs),'usage_s':sum(x['usage_s'] for x in jobs),'n_qpy':len(execution),'result_rows':len(res),'hw_rows':len(hw),'drift_rows':len(d),'drift_flags':int(flags.sum()),'hardware_statuses':status,'nonfinite_no_reference':len(invalid_no_ref),'hash_ledger_missing_hardware_files':sorted(unlisted),'current_release_nonlog_mismatches':mismatch,'qpy_errors':qpy_errors[:10]}
(OUT/'audit_metrics.json').write_text(json.dumps(summary,indent=2,default=int))
for c in records:print(c['result'],c['check'],':',c['detail'])
print('TOTAL',summary['checks'])
