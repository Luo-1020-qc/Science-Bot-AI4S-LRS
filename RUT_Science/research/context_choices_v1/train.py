"""Train a contextual choice matcher on frozen synthetic requests, entirely offline."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'RUT_Science'))
from rut_science.science_bot.general.planning.choices import INTENTS,DIM,VERSION,vector,keyword_intent,SCOPES,BASE

HERE=Path(__file__).resolve().parent
PHRASES={
 'comparison':['我想比较{topic}的两种方案，保持条件一致。','帮我对比{topic}的候选与基线，判断差异。','关于{topic}，先看同等预算下谁的表现更好。','我想知道{topic}的新方法比简单基线有无优势。','对{topic}做公平比较，先固定数据和评估方式。','我的目标是评估{topic}不同方案的误差和成本差异。','希望比较{topic}的效果，允许没有差异。','我想比较{topic}，先澄清适用范围、实验单位和验收标准。'],
 'prediction':['我想预测{topic}中未见对象的结果。','关于{topic}，重点评估独立留出数据上的预测能力。','希望用{topic}历史数据预测未来，不让未来信息泄漏。','对{topic}建立预测评估，区分训练验证与最终测试。','我想知道{topic}模型能否泛化到新对象。','请规划{topic}在未来时间段上的预测验证。','关注{topic}的新样本预测误差和留出划分。','我的目标是预测{topic}未见样本，而非解释因果。'],
 'replication':['我想复现{topic}论文中的核心结论。','关于{topic}，先把原论文的适用条件和实现对齐。','希望重现{topic}文章的结果，并记录实现差异。','对{topic}做论文复现，先选定具体命题。','我想核对{topic}已发表方法能否被独立复现。','请帮我制定{topic}最小复现流程。','按{topic}原文核对数据、配置和评估，再复现。','我的目标是复刻{topic}选定论文的实验条件。'],
 'causal':['我想估计对{topic}实施干预的因果效应。','关于{topic}，重点核查混杂与因果识别条件。','希望判断{topic}干预是否导致结局变化。','对{topic}设计随机分配研究来估计干预效应。','我想知道{topic}变化能否归因于所施加的处理。','请先审查{topic}观察数据支持因果结论的条件。','聚焦{topic}目标干预与反事实比较。','我的目标是识别{topic}处理对主要结局的因果效应。'],
 'exploration':['我想探索{topic}中的现象与关联，先不预设方向。','关于{topic}，先筛选值得继续验证的因素。','希望对{topic}做探索性先导，形成研究假设。','对{topic}先找可能的机制，之后独立验证。','我想先描述{topic}数据的模式，不声称因果。','请规划{topic}的探索性分析，不预设谁更好。','先探索{topic}是否有值得检验的现象。','我的目标是从{topic}数据提出候选问题。'],
 'general':['我对{topic}有想法，但还不知道应该问什么。','帮我把{topic}这个课题的边界逐步说清楚。','希望先讨论{topic}的应用场景和资源限制。','关于{topic}，我还没有选定研究目的。','我想开始{topic}研究，先让我选择合适的方向。','先把{topic}从模糊想法整理成研究计划。','关于{topic}，先确认我到底想解决什么问题。','我希望针对{topic}逐项确定实验边界。'],
}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


def prepare():
    if (HERE/'dataset.json').exists():raise ValueError('Dataset exists; use a new experiment version')
    sources={'train':['候选模型','电池材料','合成传感器','细胞图像','表格模型','反应条件'],
        'dev':['设备状态','合成流场'],'test':['LinearNO与FNO','土壤数据','弹性场','时序模型']}
    rows=[]
    for split,topics in sources.items():
        for topic in topics:
            for intent,phrases in PHRASES.items():
                for index,phrase in enumerate(phrases):
                    rows.append({'split':split,'source_group':topic,'case_id':split+'_'+str(len(rows)),
                        'request':phrase.format(topic=topic),'intent':intent,'label_source':'scripted_synthetic_not_expert'})
    dump(HERE/'dataset.json',rows)
    dump(HERE/'dataset_manifest.json',{'sha256':{'dataset.json':sha(HERE/'dataset.json')},'source_groups':sources,
        'human_labels':0,'limitation':'Disjoint topic groups share request templates and scripted intent labels; not a blind scientific or user study.'})
    print('Prepared synthetic contextual requests:',len(rows))


def data():
    manifest=json.loads((HERE/'dataset_manifest.json').read_text(encoding='utf-8'))
    if manifest['sha256']['dataset.json']!=sha(HERE/'dataset.json'):raise ValueError('Frozen choice data changed')
    rows=json.loads((HERE/'dataset.json').read_text(encoding='utf-8'))
    groups={s:{r['source_group'] for r in rows if r['split']==s} for s in ('train','dev','test')}
    if any(groups[a]&groups[b] for a,b in [('train','dev'),('train','test'),('dev','test')]):raise ValueError('Choice source groups overlap')
    return rows


def fit(rows):
    train=[r for r in rows if r['split']=='train']
    x=np.array([vector(r['request']) for r in train])
    y=np.array([INTENTS.index(r['intent']) for r in train])
    target=np.eye(len(INTENTS))[y]
    w=np.zeros((len(INTENTS),DIM))
    for _ in range(600):
        logits=x@w.T
        logits-=logits.max(axis=1,keepdims=True)
        p=np.exp(logits);p/=p.sum(axis=1,keepdims=True)
        w-=1.5*((p-target).T@x/len(x)+0.0005*w)
    return w.tolist(),{'epochs':600,'learning_rate':1.5,'l2':0.0005,'training_requests':len(train),
        'parameter_l2_change':float(np.linalg.norm(w)),'algorithm':'softmax_behavior_cloning_of_scripted_intents'}


def predict(text,weights):
    x=vector(text)
    scores=[sum(a*b for a,b in zip(row,x)) for row in weights]
    return INTENTS[max(range(len(scores)),key=scores.__getitem__)]


def evaluate(rows,weights):
    results={}
    for split in ('train','dev','test'):
        selected=[r for r in rows if r['split']==split]
        results[split]={'cases':len(selected),'keyword_correct':sum(keyword_intent(r['request'])==r['intent'] for r in selected),
            'trained_correct':sum(predict(r['request'],weights)==r['intent'] for r in selected)}
    samples=[]
    for text in ('我想比较两种模型，先澄清适用范围、实验单位和验收标准。',
                 '我想预测新对象上的结果，请避免数据泄漏。','我希望复现选定论文里的核心命题。'):
        intent=predict(text,weights)
        samples.append({'request':text,'predicted_intent':intent,
                        'scope_choices':[{'label':a,'value':b} for a,b in SCOPES.get(intent,BASE['scope'])]})
    return results,samples


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--output',type=Path,default=HERE/'run_001')
    args=parser.parse_args()
    if args.prepare:prepare();return
    args.output.mkdir(parents=True,exist_ok=False)
    rows=data();weights,training=fit(rows)
    dump(args.output/'policy.json',{'version':VERSION,'intents':list(INTENTS),'dimensions':DIM,'weights':weights,
        'dataset_sha256':sha(HERE/'dataset.json'),'training_source':'scripted_synthetic_not_expert',
        'language_model_weights_changed':False,'purpose':'Match user needs to prospective choice families; not factual inference'})
    evaluation,samples=evaluate(rows,weights)
    dump(args.output/'examples.json',samples)
    dump(args.output/'results.json',{'training':training,'evaluation':evaluation,'human_labels':0,
        'model_requests':0,'real_experiments':0,'understanding_improvement_measured':False,
        'limitation':'Intent accuracy on shared synthetic templates does not measure human option usefulness or end-to-end research quality.'})
    dump(args.output/'manifest.json',{'sha256':{p.name:sha(p) for p in sorted(args.output.glob('*.json'))},
                                    'training_source_sha256':sha(Path(__file__))})
    print(json.dumps(evaluation))


if __name__=='__main__':main()
