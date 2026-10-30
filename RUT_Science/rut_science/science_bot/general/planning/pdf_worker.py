"""Private parser entry: receives bounded bytes, follows no URLs or PDF actions."""
import base64
import io
import json
import logging
import re
import sys


def parse(request):
    import pypdf
    raw=base64.b64decode(request['data'],validate=True)
    if len(raw)>16*1024*1024:raise ValueError('PDF超过16 MiB。')
    reader=pypdf.PdfReader(io.BytesIO(raw),strict=False)
    if reader.is_encrypted:raise ValueError('暂不读取加密PDF，请先提供已解密的副本。')
    count=len(reader.pages);start,end=request['start_page'],request['end_page']
    if not 1<=start<=end<=count or end-start+1>12:raise ValueError('页码超出范围；此PDF共'+str(count)+'页，每次最多12页。')
    rows=[]
    for number in range(start,end+1):
        page=reader.pages[number-1];stream=page.get_contents()
        if stream is not None and len(stream.get_data())>4*1024*1024:raise ValueError('PDF页内容过大，请先检查第'+str(number)+'页。')
        text=page.extract_text() or ''
        text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]','',text).strip()
        if len(re.findall(r'[\w\u4e00-\u9fff]',text))<12:
            raise ValueError('第'+str(number)+'页缺少可靠文本，可能是扫描件/图片页；请先OCR或选择文字页。')
        if text.count('\ufffd')>max(3,len(text)//50):raise ValueError('第'+str(number)+'页存在较多乱码，请先校对提取文本。')
        rows.append({'page':number,'text':text})
        if sum(len(r['text'].encode('utf-8')) for r in rows)>18000:raise ValueError('所选页文字超过18000字节，请缩小页码范围；未截断。')
    return {'page_count':count,'pages':rows,'extractor':'pypdf-'+pypdf.__version__}


if __name__=='__main__':
    logging.disable(logging.CRITICAL)
    try:
        incoming=sys.stdin.buffer.read(24*1024*1024+1)
        if len(incoming)>24*1024*1024:raise ValueError('PDF输入过大。')
        result=parse(json.loads(incoming))
    except Exception as exc:
        result={'error':str(exc)[:200] if isinstance(exc,ValueError) else 'PDF无法解析，请检查文件。'}
    sys.stdout.buffer.write(json.dumps(result,ensure_ascii=False).encode('utf-8'))
