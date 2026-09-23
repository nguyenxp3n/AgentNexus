from __future__ import annotations
import json
from pathlib import Path
import networkx as nx,yaml
from pydantic import BaseModel,ConfigDict,Field
from orch.models.task import ProjectPlan
from orch.models.state import TaskState
class PlanValidationResult(BaseModel):
    model_config=ConfigDict(extra='forbid')
    ok:bool; cycles:list[list[str]]=Field(default_factory=list); missing_dependencies:list[str]=Field(default_factory=list); self_dependencies:list[str]=Field(default_factory=list)
def load_plan(path:Path)->ProjectPlan:
    raw=Path(path).read_text(); data=json.loads(raw) if Path(path).suffix.lower()=='.json' else yaml.safe_load(raw); return ProjectPlan.model_validate(data)
class DagPlan:
    def __init__(self,plan:ProjectPlan,graph:nx.DiGraph):self.plan=plan;self.graph=graph;self.tasks={t.id:t for t in plan.tasks}
    @classmethod
    def from_plan(cls,plan:ProjectPlan):
        g=nx.DiGraph(); ids={t.id for t in plan.tasks}; g.add_nodes_from(ids)
        for t in plan.tasks:
            for d in t.dependencies:
                if d in ids:g.add_edge(d,t.id)
        return cls(plan,g)
    def validate(self)->PlanValidationResult:
        ids=set(self.tasks); missing=[]; selfdeps=[]
        for t in self.plan.tasks:
            for d in t.dependencies:
                if d not in ids:missing.append(f'{t.id}:{d}')
                if d==t.id:selfdeps.append(t.id)
        cycles=[]
        if not nx.is_directed_acyclic_graph(self.graph):
            for c in nx.simple_cycles(self.graph):
                if c:cycles.append(c+[c[0]])
        return PlanValidationResult(ok=not(missing or selfdeps or cycles),cycles=cycles,missing_dependencies=sorted(missing),self_dependencies=sorted(set(selfdeps)))
    def execution_waves(self)->list[list[str]]:
        if not nx.is_directed_acyclic_graph(self.graph):return []
        return [sorted(list(g)) for g in nx.topological_generations(self.graph)]
    def dependencies_satisfied(self,task_id:str,states:dict[str,TaskState],policy:str='integrated')->bool:
        required=TaskState.AUDITED if policy=='audited' else TaskState.COMPLETED
        return all(states.get(d)==required for d in self.tasks[task_id].dependencies)
