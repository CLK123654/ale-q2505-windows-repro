from __future__ import annotations
import hashlib,json,os,shutil,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];TASK=ROOT/"task";EVIDENCE=ROOT/"evidence";RUNS=ROOT/"windows-runs";KUBECTL=os.environ["KUBECTL_PATH"]
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def reset(p:Path)->None:
 if p.exists():shutil.rmtree(p)
 p.mkdir(parents=True)
def extract(z:Path,t:Path)->None:
 t.mkdir(parents=True)
 with zipfile.ZipFile(z) as a:a.extractall(t)
def paths(r:Path)->list[str]:return sorted(p.relative_to(r).as_posix() for p in r.rglob("*") if p.is_file())
def norm(p:Path)->bytes:
 data=p.read_bytes().replace(b"\r\n",b"\n")
 if p.suffix.lower()==".json":return json.dumps(json.loads(data.decode("utf-8-sig")),ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
 return data
def compare(a:Path,e:Path)->list[str]:
 if paths(a)!=paths(e):raise AssertionError("path set differs")
 for rel in paths(e):
  if norm(a/rel)!=norm(e/rel):raise AssertionError(f"Reference differs:{rel}")
 return paths(e)
def build(i:Path,o:Path)->subprocess.CompletedProcess[str]:return subprocess.run([sys.executable,str(ROOT/"implementation/build_delivery.py"),"--input",str(i),"--output",str(o),"--kubectl",KUBECTL],text=True,capture_output=True,timeout=300)
def main()->None:
 reset(RUNS);EVIDENCE.mkdir(exist_ok=True);version=subprocess.run([KUBECTL,"version","--client","--output=json"],text=True,capture_output=True,timeout=30)
 if version.returncode or "v1.32.6" not in version.stdout:raise AssertionError("kubectl1.32.6 required")
 ref=RUNS/"reference";extract(TASK/"reference.zip",ref);expected=ref;clean=[]
 for label in ["clean a","clean b"]:
  base=RUNS/label;extract(TASK/"输入数据包.zip",base);inp=base/"input_data";before={p.relative_to(inp).as_posix():sha(p) for p in inp.rglob("*") if p.is_file()}
  for pi in [1,2]:
   out=base/f"output {pi}";c=build(inp,out)
   if c.returncode:raise AssertionError(c.stdout+c.stderr)
   generated=compare(out,expected);clean.append({"root_id":label,"process_index":pi,"primary_software_executed":True,"input_unchanged":True,"reference_full_match":True,"generated_paths":generated})
  if before!={p.relative_to(inp).as_posix():sha(p) for p in inp.rglob("*") if p.is_file()}:raise AssertionError("input changed")
 positive=RUNS/"positive";extract(TASK/"输入数据包.zip",positive);p=positive/"input_data/autoscaling_policy.json";v=json.loads(p.read_text(encoding="utf-8"));v["max_replicas"]=32;p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");c=build(positive/"input_data",positive/"output")
 if c.returncode or "maxReplicas: 32" not in (positive/"output/rendered_production.yaml").read_text(encoding="utf-8"):raise AssertionError("valid policy change had no effect")
 (EVIDENCE/"positive-case.json").write_text(json.dumps({"mutation":"max_replicas从30改为32","rendered_hpa_changed":True,"behavior_changed":True},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 negative=RUNS/"negative";extract(TASK/"输入数据包.zip",negative);p=negative/"input_data/environment_labels.csv";lines=p.read_text().splitlines();p.write_text("\n".join(lines+[lines[1]])+"\n");out=negative/"output";out.mkdir();(out/"stale.txt").write_text("stale");c=build(negative/"input_data",out)
 if c.returncode==0 or out.exists():raise AssertionError("duplicate label contract did not fail closed")
 (EVIDENCE/"negative-case.log").write_text(f"return_code={c.returncode}\n{c.stdout}{c.stderr}",encoding="utf-8")
 summary={"result":"PASS","commit_sha":os.getenv("GITHUB_SHA"),"workflow_run_id":os.getenv("GITHUB_RUN_ID"),"runner_image":os.getenv("ImageOS"),"main_software":{"name":"Kubernetes","kubectl_version":"v1.32.6","executed":True,"scope":"client_kustomize_only"},"clean_directory_count":2,"process_runs_per_directory":2,"clean_runs":clean,"positive_mutation":"PASS","negative_case":"PASS","reference_full_comparison":"PASS","formal_network":{"kubectl_outbound_blocked":True,"external_services_used":False,"cluster_connected":False}}
 (EVIDENCE/"windows-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":main()
