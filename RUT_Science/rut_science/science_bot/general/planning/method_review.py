"""Conservative declaration contradictions, never a scientific-validity certificate.

These bounded patterns flag concrete assertions and local negations. They do
not establish independence, external evidence quality or statistical validity.
"""
import re


def _clauses(value):
    return [s.strip() for s in re.split(r'[，,。；;\n]|(?<!\d)\.(?!\d)', value) if s.strip()]


def _asserts(value, pattern):
    for clause in _clauses(value):
        for match in re.finditer(pattern, clause, re.I):
            prefix=clause[max(0,match.start()-18):match.start()]
            if re.search(r'(?:并非|不是)\s*$',prefix) and re.match(r'没有|不存在|无',match[0]):
                continue
            if re.search(r'(?:不|不能|不得|不要|禁止|避免|不会|不应|不把|不允许|not\s+|never\s+|do not\s+)[^，。；;]{0,5}$',prefix,re.I):
                continue
            if re.search(r'不(?:把|将)[^，。；;]{0,18}$',prefix):
                continue
            if re.search(r'(?:不能|不得|不要|禁止|不应)(?:不报告|不记录|不披露|忽略|隐瞒|删除)',match[0]):
                continue
            if re.search(r'(?:不|不能|不得|不要|禁止|not\s+)\s*(?:用于|用来|参与|指导|调参|选择|作为|视为|当作|当成|算作)',match[0],re.I):
                continue
            return True
    return False


def risks(state):
    def text(field):
        return '' if field in state.get('unknown',[]) else state.get('facts',{}).get(field,{}).get('value','')
    rows=[]
    def flag(field,code,detail):
        rows.append({'field':field,'code':code,'status':'blocked','detail':detail,'category':'method_risk'})
    unit=text('experimental_unit');analysis=text('analysis');sampling=text('sampling')
    if text('design').startswith('paired') and _asserts(unit,
            r'(?:没有|不存在|缺少|无|no\s+|without\s+).{0,14}(?:同一单位|配对|匹配|matching|pairing)|互不相关.{0,16}(?:强行|直接)配对'):
        flag('experimental_unit','pairing_basis_denied','声明否定了单位内或匹配关系，不能仅因数量相等强行配对；请修订设计或提供真实匹配依据。')
    if _asserts(unit,r'(?:网格点|像素|技术重复|测量读数).{0,22}(?:视为|作为|当作|当成|算作|为).{0,10}独立(?:样本|重复|单位|配对)') or _asserts(analysis,r'(?:以|按|将).{0,4}(?:网格点|像素|技术重复).{0,8}(?:重采样|bootstrap)'):
        flag('experimental_unit','technical_measurement_as_replication','声明把技术测量用于独立重复或重采样；应核实真实推断单位及相关结构，不能以测量点数扩大独立样本。')
    split='；'.join(text(f) for f in ('data_source','sampling','analysis','baseline'))
    if _asserts(split,r'(?:用|根据|依据|按|利用|以).{0,10}(?:最终测试|测试集|测试误差|测试结果|test(?: set)?).{0,18}(?:选择|选|调参|调优|优化|tune|select)|(?:最终测试|测试集|test set).{0,12}(?:用于|用来|参与|指导).{0,12}(?:调参|调优|选择|选模|tuning|selection)'):
        flag('data_source','final_test_used_for_selection','最终测试被声明用于选择模型或超参数，与冻结后评估的职责冲突；请改用开发/验证数据并保留独立最终评估。')
    if _asserts(sampling,r'(?:保证|确保).{0,12}(?:功效|power)|(?:功效|power).{0,12}(?:保证|确保)') and re.search(r'默认|模板|补值|编造|假定|没有先导|无先导|default|template|invented',sampling,re.I):
        flag('sampling','fabricated_power_basis','默认、模板或假定参数不能成为已验证的功效保证；请保留来源缺口或明确先导/敏感性分析。')
    acceptance=text('acceptance')
    if _asserts(acceptance,r'(?:阴性|负结果|不显著|不确定|negative|null).{0,8}(?:不(?:予|再)?(?:报告|记录|披露)|丢弃|删除|隐瞒|忽略|隐藏|不报)|只(?:报告|保留).{0,10}(?:阳性|显著|正向)|(?:隐瞒|删除|忽略).{0,8}(?:阴性|负结果|不显著)'):
        flag('acceptance','negative_results_suppressed','声明包含不报告或隐藏阴性/不确定结果的规则；验收须如实记录全部结果与偏离。')
    if _asserts(acceptance+'；'+text('resources'),r'(?:一直|继续|反复).{0,8}(?:试到|做到|跑到|直到).{0,8}显著|(?:预算)?上限.{0,16}(?:提高|增加|追加).{0,8}(?:预算|经费)|按(?:显著|结果|分数).{0,8}(?:追加|加|增加).{0,5}预算'):
        flag('acceptance','outcome_driven_budget_or_stopping','声明要求追逐显著性或按结果突破资源上限；请预先锁定停止和升级条件。')
    return rows


def notice(assessment):
    declaration='已齐全' if assessment.get('declarations_complete',False) else '仍有未决项'
    count=len(assessment.get('method_risks',[]))
    return '声明状态：'+declaration+'；方法状态：'+('发现'+str(count)+'项风险，需修订或人工核查。' if count else '待人工复核，尚未验证科学有效性。')
