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
    if len(raw)>64*1024*1024:raise ValueError('PDF超过64 MiB。')
    reader=pypdf.PdfReader(io.BytesIO(raw),strict=False)
    if reader.is_encrypted:raise ValueError('暂不读取加密PDF，请先提供已解密的副本。')
    count=len(reader.pages)
    if request.get('inspect'):
        if count<1:raise ValueError('PDF没有可读取的页面。')
        return {'page_count':count,'extractor':'pypdf-'+pypdf.__version__}
    start=request['start_page'];end=request.get('end_page') or count
    if not 1<=start<=end<=count or end-start+1>256:raise ValueError('页码超出范围；此PDF共'+str(count)+'页，每次最多256页。')
    rows=[]
    for number in range(start,end+1):
        page=reader.pages[number-1];stream=page.get_contents()
        if stream is not None and len(stream.get_data())>4*1024*1024:raise ValueError('PDF页内容过大，请先检查第'+str(number)+'页。')
        text=page.extract_text() or ''
        text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]','',text).strip()
        if not text.strip() and len(page.images):
            raise ValueError('第'+str(number)+'页缺少可靠文本，可能是扫描件/图片页；请先OCR或选择文字页。')
        if text.count('\ufffd')>max(3,len(text)//50):raise ValueError('第'+str(number)+'页存在较多乱码，请先校对提取文本。')
        rows.append({'page':number,'text':text})
        if sum(len(r['text'].encode('utf-8')) for r in rows)>2*1024*1024:raise ValueError('提取文字超过2 MiB，请缩小页码范围；未截断。')
    return {'page_count':count,'pages':rows,'extractor':'pypdf-'+pypdf.__version__}


if __name__=='__main__':
    logging.disable(logging.CRITICAL)
    try:
        incoming=sys.stdin.buffer.read(90*1024*1024+1)
        if len(incoming)>90*1024*1024:raise ValueError('PDF输入过大。')
        result=parse(json.loads(incoming))
    except Exception as exc:
        result={'error':str(exc)[:200] if isinstance(exc,ValueError) else 'PDF无法解析，请检查文件。'}
    sys.stdout.buffer.write(json.dumps(result,ensure_ascii=False).encode('utf-8'))
