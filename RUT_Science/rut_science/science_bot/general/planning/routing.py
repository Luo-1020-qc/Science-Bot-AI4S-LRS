"""Host-only planning intent, preserving explicit file and execution boundaries."""
import re

REVISION = re.compile(r'^(?:更正|修正|修改为|改成|改为|纠正|更新预算|调整预算|correction\b|revise\b)\s*[:：\s]', re.I)


def revision_content(text):
    return re.sub(r'^(?:更正|修正|修改为|改成|改为|纠正|correction\b|revise\b)\s*[:：]\s*','',text,count=1,flags=re.I)


def is_revision(text):
    return bool(REVISION.search(text) or re.search(
        r'^(?:现在|这次|本轮)(?:我|我们)?(?:要|想)?(?:改为|改成|换成)|^(?:研究目标|研究目的|目标)改为|^(?:请)?(?:把|将)?(?:预算|时间上限|资源边界|资源上限)(?:改为|改成|调整为|缩减为)', text))


def natural_start(text):
    if not isinstance(text, str) or text.lstrip().startswith('/'):
        return False
    if re.fullmatch(r'(?:请)?(?:设计|规划)(?:一个)?实验[。.!！]?',text.strip()):
        return False
    if re.match(r'^(?:什么是|解释|请解释|介绍|为什么|what\s+is|explain\b)', text.strip(), re.I):
        return False
    subject = r'实验|科研|研究|课题|论文|模型|方法|材料|数据|预测|比较|复现|先导|study|experiment|model|paper|research'
    domain = r'实验|科研|研究|课题|论文|模型|方法|材料|数据|先导|CViT|FNO|Darcy|study|experiment|model|paper|research'
    return bool(
        re.search(r'(?:规划|计划|设计|方案|plan\b|design\b).{0,100}(?:'+subject+r')|(?:'+subject+r').{0,100}(?:规划|计划|设计|方案|plan\b|design\b)', text, re.I)
        or re.search(r'(?:我|我们)?(?:想|希望|准备|打算)(?:要)?(?:比较|研究|复现|验证|评估|预测)', text) and re.search(domain,text,re.I)
        or re.search(r'\b(?:help\s+(?:me|us)|I\s+want|we\s+want|we\s+need)\b.{0,80}\b(?:plan|design|study|compare|replicate|evaluate)\b', text, re.I)
        or re.search(r'(?:我的|我们的).{0,15}(?:模型|研究|实验).{0,20}(?:没思路|效果不好|不知道)', text))


def explicit_external_task(text, request):
    if request.input_paths:
        return True
    if re.match(r'^(?:请|帮我|现在|立即|直接|开始|马上|\s)*(?:读取|阅读|打开|列出|浏览|查看文件|总结文件|read\b|list\b)', text, re.I):
        return True
    if re.match(r'^训练(?:与|和|集|数据|预算|划分|/|、)',text):return False
    if re.match(r'^(?:请|帮我|现在|立即|直接|开始|马上|\s)*(?:运行|执行|启动|训练|拟合|run\b|execute\b|train\b)', text, re.I):
        return not re.search(r'只(?:做)?规划|仅(?:做)?规划|先规划|不要执行|不执行|不要运行', text)
    return False


def route_override(session, text, request):
    text = text.strip()
    if not text:return False
    if text.split(maxsplit=1)[0] == '/plan':
        return True
    if text.startswith('/') or request.intent == 'research' or explicit_external_task(text, request):
        return False
    if re.search(r'访谈|逐步设计|一步步.{0,8}实验|design interview', text, re.I):
        return False
    if natural_start(text):
        return True
    from .ledger import load
    state = load(session)
    if not state or not state['active']:
        return False
    if re.match(r'^(?:换个话题|先不谈|不讨论|不要规划|停止规划|今天天气|翻译|写一首|你好|谢谢|hi\b|hello\b|translate\b)', text, re.I):
        return False
    if re.search(r'手机|购物|餐厅|晚餐',text) and not re.search(r'实验|科研|研究|模型|设计|规划',text):
        return False
    if re.match(r'^(?:什么是|介绍|解释|如何|怎么|为什么|what\b|why\b|how\b)', text, re.I) and not re.search(
            r'实验|方案|设计|研究|单位|方差|功效|验收|指标|基线|数据|因果|预测|预算|plan|design|unit|power', text, re.I):
        return False
    return True
