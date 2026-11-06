"""Permanent runner utility; only temporary data lives in issue comments."""
import argparse,base64,hashlib,io,json,os,re,subprocess,tempfile,zipfile
from pathlib import Path
REPO='NogeomHub/valhalla-routing-poc'
PLAN = {'protocol': 'A42-TRANSFER-V1', 'archiveSHA256': 'cb8a062139fb6332a4a51e4e542c70ac64e4373c14483e6100c6d684ca727c42', 'archiveBytes': 1121423, 'parts': 28, 'nonce': 'cb8a062139fb6332a4a51e4e', 'expectedAssets': {'a42-meximieux-amberieu.osm.pbf': {'bytes': 1064733, 'sha256': 'e5912f17f620535e9b3be7dbd2e2b9963c778a7d1a873614b6ae901d1b793235'}, 'a42-extraction-manifest.json': {'bytes': 52457, 'sha256': '7814479e586f7c99e26a608f8c1bd091cd14681aeb7dbffed6e1bc67ca6ecb3c'}, 'a42-extraction-audit.json': {'bytes': 3437, 'sha256': 'f79369e3e22af083953f4870d5743a631d17187e19857b43aa0ca1eefa47d504'}, 'SHA256SUMS': {'bytes': 284, 'sha256': '3075743f2b105afae5405d925c2be726a56e4984f63a8add28258edde45aa1e3'}}, 'releaseId': 436368655, 'tag': 'a42-pilot-20261102-v1'}
def sha(b):return hashlib.sha256(b).hexdigest()
def verify_bundle(raw):
 if len(raw)!=PLAN['archiveBytes'] or sha(raw)!=PLAN['archiveSHA256']:raise RuntimeError('BUNDLE_INTEGRITY_FAILED')
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  if len(z.namelist())!=4 or set(z.namelist())!=set(PLAN['expectedAssets']):raise RuntimeError('ASSET_INVENTORY_FAILED')
  result={}
  for name,spec in PLAN['expectedAssets'].items():
   data=z.read(name)
   if len(data)!=spec['bytes'] or sha(data)!=spec['sha256']:raise RuntimeError('ASSET_INTEGRITY_FAILED: '+name)
   result[name]=data
 return result
def api(path,method='GET',payload=None):
 command=['gh','api','--method',method,path]
 if payload is not None:command+=['--input','-']
 r=subprocess.run(command,input=json.dumps(payload) if payload is not None else None,text=True,capture_output=True,check=True)
 return json.loads(r.stdout) if r.stdout.strip() else None
def comments_all(number):
 result=[]
 for page in range(1,11):
  batch=api(f'repos/{REPO}/issues/{number}/comments?per_page=100&page={page}')
  result.extend(batch)
  if len(batch)<100:return result
 raise RuntimeError('COMMENT_PAGINATION_LIMIT_REQUIRES_MANUAL_REVIEW')

def cleanup(number):
 if os.environ.get('GITHUB_REPOSITORY')!=REPO or not number or number<=0:raise RuntimeError('WRONG_CLEANUP_CONTEXT')
 issue=api(f'repos/{REPO}/issues/{number}')
 if 'pull_request' in issue:raise RuntimeError('NOT_A_TRANSFER_ISSUE')
 body=json.loads(issue['body'])
 if body!=PLAN:
  if body.get('releaseId')==PLAN['releaseId'] and body.get('transferCleaned') is True:return
  # Successful upload already cleaned its comments and closed the issue.
  if body.get('releaseId')==PLAN['releaseId'] and body.get('verified') is True and issue['state']=='closed':return
  raise RuntimeError('WRONG_TRANSFER_ISSUE')
 comments=comments_all(number)
 prefix='A42-TRANSFER-V1:'+PLAN['nonce']+':'
 for c in comments:
  if c.get('body','').startswith(prefix):api(f'repos/{REPO}/issues/comments/{c["id"]}',method='DELETE')
 receipt={'releaseId':PLAN['releaseId'],'transferCleaned':True,'verificationResult':'See workflow log; cleanup does not imply upload success','releasePublication':'Not performed'}
 api(f'repos/{REPO}/issues/{number}',method='PATCH',payload={'state':'closed','body':json.dumps(receipt,indent=2)})
 print('Transfer comments removed. Release unchanged. Failed run requires restaging before retry.')

def main():
 p=argparse.ArgumentParser();p.add_argument('--issue',type=int);p.add_argument('--cleanup-issue',type=int);p.add_argument('--check-local',type=Path);a=p.parse_args()
 if a.cleanup_issue:
  cleanup(a.cleanup_issue);return
 if a.check_local:
  verify_bundle(a.check_local.read_bytes());print('Local archive + 4 assets verified; no network call.');return
 if not a.issue or a.issue<=0:raise RuntimeError('ISSUE_REQUIRED')
 if os.environ.get('GITHUB_REPOSITORY')!=REPO:raise RuntimeError('WRONG_REPOSITORY')
 release=api(f'repos/{REPO}/releases/{PLAN["releaseId"]}')
 if not release['draft'] or release['tag_name']!=PLAN['tag']:raise RuntimeError('EXISTING_DRAFT_MISMATCH')
 issue=api(f'repos/{REPO}/issues/{a.issue}')
 if 'pull_request' in issue:raise RuntimeError('NOT_AN_ISSUE')
 if json.loads(issue['body'])!=PLAN:raise RuntimeError('TRANSFER_PLAN_MISMATCH')
 comments=comments_all(a.issue);parts={};ids=[]
 for c in comments:
  body=c.get('body','');header,separator,part=body.partition('\n')
  m=re.fullmatch(r'A42-TRANSFER-V1:'+re.escape(PLAN['nonce'])+r':(\d+)/(\d+)',header)
  if not m:continue
  i,n=map(int,m.groups())
  if n!=PLAN['parts'] or i in parts or not 1<=i<=n:raise RuntimeError('CHUNK_INVENTORY_FAILED')
  parts[i]=part;ids.append(c['id'])
 if set(parts)!=set(range(1,PLAN['parts']+1)):raise RuntimeError('CHUNK_MISSING')
 assets=verify_bundle(base64.b64decode(''.join(parts[i] for i in sorted(parts)),validate=True))
 existing={x['name'] for x in release['assets']}
 if existing-set(assets):raise RuntimeError('UNEXPECTED_EXISTING_ASSET')
 with tempfile.TemporaryDirectory() as t:
  root=Path(t);names=[]
  for name,data in assets.items():
   f=root/name;f.write_bytes(data)
   if name not in existing:names.append(str(f))
  if names:subprocess.run(['gh','release','upload',PLAN['tag'],'--repo',REPO,*names],check=True)
  updated=api(f'repos/{REPO}/releases/{PLAN["releaseId"]}')
  if not updated['draft'] or {x['name'] for x in updated['assets']}!=set(assets):raise RuntimeError('REMOTE_ASSET_INVENTORY_FAILED')
  download=root/'verified';download.mkdir()
  subprocess.run(['gh','release','download',PLAN['tag'],'--repo',REPO,'--dir',str(download)],check=True)
  for name,spec in PLAN['expectedAssets'].items():
   data=(download/name).read_bytes()
   if len(data)!=spec['bytes'] or sha(data)!=spec['sha256']:raise RuntimeError('REMOTE_ASSET_INTEGRITY_FAILED: '+name)
 # No release edit/create/publication command exists in this utility.
 receipt={'verified':True,'releaseStillDraft':True,'releaseId':PLAN['releaseId'],'assets':PLAN['expectedAssets']}
 summary=os.environ.get('GITHUB_STEP_SUMMARY')
 if summary:Path(summary).write_text('# A42 release assets verified\n\nRelease remains DRAFT.\n\n```json\n'+json.dumps(receipt,indent=2)+'\n```\n')
 # Remove only this transfer's chunks AFTER successful remote verification.
 for ident in ids:api(f'repos/{REPO}/issues/comments/{ident}',method='DELETE')
 api(f'repos/{REPO}/issues/{a.issue}',method='PATCH',payload={'state':'closed','body':json.dumps(receipt,indent=2)})
 print('Four assets verified remotely. Draft preserved. Transfer comments removed.')
if __name__=='__main__':main()
