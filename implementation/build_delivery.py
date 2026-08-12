from __future__ import annotations
import argparse,csv,json,shutil,subprocess,tempfile
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parent;REQUIRED={"README.txt","autoscaling_policy.json","environment_labels.csv","current/deployment.yaml","current/hpa.yaml"}
def run(cmd:list[str])->subprocess.CompletedProcess[str]:return subprocess.run(cmd,text=True,capture_output=True,timeout=180)
def load(path:Path)->dict:return yaml.safe_load(path.read_text(encoding="utf-8"))
def dump(path:Path,value:dict)->None:path.write_text(yaml.safe_dump(value,sort_keys=False,allow_unicode=True),encoding="utf-8")
def main()->None:
 p=argparse.ArgumentParser();p.add_argument("--input",required=True);p.add_argument("--output",required=True);p.add_argument("--kubectl",required=True);a=p.parse_args();inp=Path(a.input).resolve();out=Path(a.output).resolve()
 if out.exists():shutil.rmtree(out)
 present={x.relative_to(inp).as_posix() for x in inp.rglob("*") if x.is_file()}
 if present!=REQUIRED:raise ValueError("交接材料集合发生变化")
 policy=json.loads((inp/"autoscaling_policy.json").read_text(encoding="utf-8"));labels=list(csv.DictReader((inp/"environment_labels.csv").open(encoding="utf-8",newline="")))
 if len(labels)!=1 or labels[0]["environment"]!="production" or labels[0]["namespace"]!=policy["namespace"]:raise ValueError("production标签合同不完整")
 current_deployment=load(inp/"current/deployment.yaml");current_hpa=load(inp/"current/hpa.yaml")
 if current_deployment["metadata"]["name"]!=policy["workload"] or current_deployment["metadata"]["namespace"]!=policy["namespace"]:raise ValueError("Deployment身份与容量合同不一致")
 temp=Path(tempfile.mkdtemp(prefix="queue-release-",dir=out.parent))
 try:
  release=temp/"release/production";evidence=temp/"evidence";release.mkdir(parents=True);evidence.mkdir()
  deployment=json.loads(json.dumps(current_deployment));hpa=json.loads(json.dumps(current_hpa));common={"platform.example/environment":"production","platform.example/owner":labels[0]["owner_label"],"platform.example/cost-center":labels[0]["cost_center_label"]}
  deployment["metadata"].setdefault("labels",{}).update(common);hpa["metadata"].setdefault("labels",{}).update(common)
  hpa["apiVersion"]="autoscaling/v2";hpa["kind"]="HorizontalPodAutoscaler";hpa["metadata"]["name"]=policy["workload"];hpa["metadata"]["namespace"]=policy["namespace"]
  hpa["spec"]={"scaleTargetRef":{"apiVersion":"apps/v1","kind":"Deployment","name":policy["workload"]},"minReplicas":policy["min_replicas"],"maxReplicas":policy["max_replicas"],"metrics":[{"type":"Resource","resource":{"name":"cpu","target":{"type":"Utilization","averageUtilization":policy["metrics"]["cpu_utilization"]}}},{"type":"External","external":{"metric":{"name":policy["metrics"]["external_name"]},"target":{"type":"AverageValue","averageValue":policy["metrics"]["external_average_value"]}}}],"behavior":{"scaleUp":{"stabilizationWindowSeconds":policy["scale_up"]["stabilization_window_seconds"],"selectPolicy":policy["scale_up"]["select_policy"],"policies":[{"type":x["type"],"value":x["value"],"periodSeconds":x["period_seconds"]} for x in policy["scale_up"]["policies"]]},"scaleDown":{"stabilizationWindowSeconds":policy["scale_down"]["stabilization_window_seconds"],"selectPolicy":policy["scale_down"]["select_policy"],"policies":[{"type":x["type"],"value":x["value"],"periodSeconds":x["period_seconds"]} for x in policy["scale_down"]["policies"]]}}}
  dump(release/"deployment.yaml",deployment);dump(release/"hpa.yaml",hpa);(release/"kustomization.yaml").write_text("apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n  - deployment.yaml\n  - hpa.yaml\n",encoding="utf-8")
  rendered=run([a.kubectl,"kustomize",str(release)])
  if rendered.returncode:raise RuntimeError(rendered.stdout+rendered.stderr)
  (evidence/"rendered.yaml").write_text(rendered.stdout,encoding="utf-8");docs=[x for x in yaml.safe_load_all(rendered.stdout) if x]
  ids=sorted(f"{x['apiVersion']}|{x['kind']}|{x['metadata'].get('namespace','')}|{x['metadata']['name']}" for x in docs);expected=sorted([f"apps/v1|Deployment|{policy['namespace']}|{policy['workload']}",f"autoscaling/v2|HorizontalPodAutoscaler|{policy['namespace']}|{policy['workload']}"])
  if ids!=expected:raise ValueError("渲染对象身份不符合发布范围")
  if deployment["spec"]!=current_deployment["spec"]:raise ValueError("Deployment业务配置发生变化")
  metric_types={x["type"] for x in hpa["spec"]["metrics"]};checks={"rendered_objects_match":ids==expected,"deployment_spec_unchanged":deployment["spec"]==current_deployment["spec"],"target_ref_match":hpa["spec"]["scaleTargetRef"]=={"apiVersion":"apps/v1","kind":"Deployment","name":policy["workload"]},"replica_bounds_match":(hpa["spec"]["minReplicas"],hpa["spec"]["maxReplicas"])==(policy["min_replicas"],policy["max_replicas"]),"metrics_match":metric_types=={"Resource","External"},"behavior_match":hpa["spec"]["behavior"]["scaleUp"]["selectPolicy"]==policy["scale_up"]["select_policy"] and hpa["spec"]["behavior"]["scaleDown"]["stabilizationWindowSeconds"]==policy["scale_down"]["stabilization_window_seconds"],"labels_match":all(x["metadata"]["labels"].items()>=common.items() for x in docs)}
  review={"status":"READY" if all(checks.values()) else "HOLD","scope":"client_render_review","kubectl_executed":True,"objects":ids,"checks":checks,"note":"候选清单只说明kubectl客户端构建结果，不代表HPA Controller已经执行扩缩容"}
  (evidence/"release_review.json").write_text(json.dumps(review,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  with (evidence/"field_review.csv").open("w",encoding="utf-8",newline="") as f:
   w=csv.writer(f,lineterminator="\n");w.writerow(["check","status","evidence"]);[w.writerow([k,"PASS" if v else "FAIL",k]) for k,v in checks.items()]
  (temp/"README.txt").write_text("这份候选包交给queue-worker发布负责人。release/production保存Deployment、HPA和Kustomize入口，evidence/rendered.yaml是kubectl客户端生成的候选清单。\n\nrelease_review.json和field_review.csv记录对象身份、容量合同、环境标签与Deployment保护结果。READY只表示发布材料可以继续审阅，不表示集群控制器已经执行扩缩容。\n",encoding="utf-8")
  if review["status"]!="READY":raise ValueError("发布材料核对未通过")
  temp.rename(out)
 except Exception:
  if temp.exists():shutil.rmtree(temp)
  if out.exists():shutil.rmtree(out)
  raise
if __name__=="__main__":main()
