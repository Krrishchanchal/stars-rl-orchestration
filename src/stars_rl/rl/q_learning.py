"""Seeded tabular Q-learning; finite-horizon terminal updates and frozen greedy use."""
from dataclasses import asdict, dataclass
import math
import random

from .actions import DEFAULT_ACTION, greedy_action, ratio
from .reward import DISCOUNT


@dataclass(frozen=True)
class LearningConfig:
    learning_rate: float = .1
    discount: float = DISCOUNT
    epsilon_start: float = 1.
    epsilon_end: float = .05
    epsilon_decay_steps: int = 1000
    seed: int = 0

    def __post_init__(self):
        for name in ('learning_rate','discount','epsilon_start','epsilon_end'):
            value=getattr(self,name)
            if type(value) not in (int,float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f'{name} must be finite in [0,1]')
        if self.learning_rate==0 or self.discount!=DISCOUNT:
            raise ValueError('positive learning rate and frozen environment discount .95 required')
        if self.epsilon_end>self.epsilon_start:
            raise ValueError('epsilon_end must not exceed epsilon_start')
        if type(self.epsilon_decay_steps) is not int or self.epsilon_decay_steps<1 or type(self.seed) is not int:
            raise ValueError('integer seed and positive decay step count required')


def checked_state(state):
    if not isinstance(state,(tuple,list)) or len(state)!=6 or any(type(v) is not int for v in state):
        raise ValueError('six integer observation fields required')
    if state[0] not in (0,1) or state[1]<1 or any(v not in (0,1,2) for v in state[2:]):
        raise ValueError('observation outside frozen schema')
    return tuple(state)


class TabularQ:
    def __init__(self, config=None):
        self.config=LearningConfig() if config is None else config
        if not isinstance(self.config,LearningConfig):raise ValueError('LearningConfig required')
        self.q={}
        self.rng=random.Random(self.config.seed)
        self.exploration_steps=0
        self.updates=0
        self.action_counts=[0]*5

    @property
    def epsilon(self):
        fraction=min(1,self.exploration_steps/self.config.epsilon_decay_steps)
        return self.config.epsilon_start+(self.config.epsilon_end-self.config.epsilon_start)*fraction

    def select(self,state,*,training=False):
        state=checked_state(state)
        if state[0]:return DEFAULT_ACTION
        if not training:return greedy_action(self.q.get(state))
        action=self.rng.randrange(5) if self.rng.random()<self.epsilon else greedy_action(self.q.get(state))
        self.exploration_steps+=1
        self.action_counts[action]+=1
        return action

    def update(self,state,action,reward,next_state,terminated):
        state=checked_state(state);ratio(action)
        if state[0]:raise ValueError('initialization excluded from learning')
        if type(terminated) is not bool or type(reward) not in (int,float) or not math.isfinite(reward):
            raise ValueError('finite reward and boolean termination required')
        if terminated:
            if next_state is not None:raise ValueError('terminal observation must be None')
            target=reward
        else:
            next_state=checked_state(next_state)
            if next_state[0] or next_state[1]!=state[1]-1:
                raise ValueError('next remaining horizon must decrease by one')
            target=reward+self.config.discount*max(self.q.get(next_state,[0.]*5))
        values=self.q.setdefault(state,[0.]*5)
        value=values[action]+self.config.learning_rate*(target-values[action])
        if not math.isfinite(value):raise ValueError('nonfinite Q update')
        values[action]=value
        self.updates+=1
        return value

    def state_dict(self):
        return dict(config=asdict(self.config),q=[dict(state=list(s),values=list(v)) for s,v in sorted(self.q.items())],
                    rng_state=self.rng.getstate(),exploration_steps=self.exploration_steps,
                    updates=self.updates,action_counts=list(self.action_counts))

    @classmethod
    def from_state_dict(cls,data):
        if type(data) is not dict or set(data)!={'config','q','rng_state','exploration_steps','updates','action_counts'}:
            raise ValueError('invalid learner state fields')
        result=cls(LearningConfig(**data['config']))
        if type(data['q']) is not list:raise ValueError('Q table must be a list')
        for row in data['q']:
            if type(row) is not dict or set(row)!={'state','values'}:raise ValueError('invalid Q row')
            state=checked_state(row['state']);values=row['values']
            if state[0] or state in result.q or type(values) is not list or len(values)!=5:
                raise ValueError('duplicate/initial Q state or invalid action domain')
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):raise ValueError('invalid Q value')
            result.q[state]=list(values)
        for field in ('exploration_steps','updates'):
            if type(data[field]) is not int or data[field]<0:raise ValueError('invalid training counter')
            setattr(result,field,data[field])
        counts=data['action_counts']
        if type(counts) is not list or len(counts)!=5 or any(type(c) is not int or c<0 for c in counts):
            raise ValueError('invalid action counts')
        if sum(counts)!=result.exploration_steps or result.updates>result.exploration_steps:
            raise ValueError('inconsistent training counters')
        result.action_counts=list(counts)
        def tuples(value):return tuple(tuples(v) for v in value) if isinstance(value,(list,tuple)) else value
        try:result.rng.setstate(tuples(data['rng_state']))
        except (ValueError,TypeError,OverflowError) as exc:raise ValueError('invalid learner RNG state') from exc
        return result
