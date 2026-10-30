"""Isolated unittest discovery with a fresh result path; no baseline rewrites."""
import argparse,io,json,os,sys,time,unittest
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--folder',required=True)
    p.add_argument('--pattern',default='test*.py');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    root=a.root.resolve();folder=root/a.folder
    sys.dont_write_bytecode=True
    for path in [folder,folder.parent,root/'RUT_Science',root/'scripts']:
        sys.path.insert(0,str(path))
    start=time.monotonic();stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.TestLoader().discover(str(folder),pattern=a.pattern))
    text=stream.getvalue();(a.output/'tests.log').write_text(text,encoding='utf-8')
    data={'passed':result.wasSuccessful(),'run':result.testsRun,'passed_tests':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
        'failures':[{'id':str(t),'traceback':e} for t,e in result.failures],
        'errors':[{'id':str(t),'traceback':e} for t,e in result.errors],
        'skipped':[{'id':str(t),'reason':r} for t,r in result.skipped],
        'seconds':round(time.monotonic()-start,3),'folder':a.folder,'pattern':a.pattern}
    (a.output/'results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k not in {'failures','errors','skipped'}},ensure_ascii=False),flush=True)
    return 0 if data['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
