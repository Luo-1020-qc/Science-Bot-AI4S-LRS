"""Lossless page chunks for reading; bounded original quotations for planning."""
from copy import deepcopy
from ....util import digest

CHUNK_BYTES=24000
CHUNK_PAGES=8


def chunks(source):
    result=[];current=[];size=0
    for page in source['pages']:
        text=page['text'];parts=[];part=[];used=0
        # A very long physical page is split without losing a character.
        for char in text:
            length=len(char.encode('utf-8'))
            if used+length>CHUNK_BYTES:
                parts.append(''.join(part));part=[];used=0
            part.append(char);used+=length
        parts.append(''.join(part))
        for text in parts:
            length=len(text.encode('utf-8'))
            if current and (size+length>CHUNK_BYTES or len(current)>=CHUNK_PAGES):
                result.append(current);current=[];size=0
            current.append({'page':page['page'],'text':text});size+=length
    if current:result.append(current)
    return result


def coverage(source,completed=0,error=''):
    rows=chunks(source)
    return {'chunk_sha256':[digest(row) for row in rows], 'total_chunks':len(rows),
            'completed_chunks':completed,'last_error':error}


def model_text(source):
    if source.get('format')!='pdf' or len(source['text'].encode('utf-8'))<=18000:
        return source['text']
    reading=source.get('interpretation') or {};covered=reading.get('coverage') or {}
    if not covered or covered.get('completed_chunks')!=covered.get('total_chunks'):
        return ''
    items=reading['items'];selected=[];used=0
    # Distribute the planning excerpt across the reading rather than taking
    # only the introduction. Complete text and every point remain in the ledger.
    count=min(len(items),64)
    indices=sorted({round(i*(len(items)-1)/max(1,count-1)) for i in range(count)})
    for index in indices:
        item=items[index];value='[PDF page '+str(item['page'])+']\n'+item['quote'][:300]
        length=len(value.encode('utf-8'))+2
        if used+length>24000:break
        selected.append(value);used+=length
    return '\n\n'.join(selected)


def model_source(source):
    from .evidence import citation
    value={'source':'evidence','key':source['id'],'text':model_text(source),
           'citation':citation(source),'status':source['status']}
    if source.get('format')=='pdf' and len(source['text'].encode('utf-8'))>18000:
        value['representation']='Grounded quotation selection from chunked reading; not the entire paper in this planning request.'
        value['reading_coverage']=deepcopy((source.get('interpretation') or {}).get('coverage'))
    return value
