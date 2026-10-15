"""Сохранение опубликованного рисунка по проверенному XML, без извлечения выводов."""
from datetime import datetime,timezone
from hashlib import sha256,md5
import json
from pathlib import Path
import re
import urllib.request
from xml.etree import ElementTree as ET
from domain.article_maps import require
from infrastructure.immutable_files import write_immutable
from infrastructure.development_prediction_store import FilePredictionStore

VERSION='xml-bound-published-figure-capture-1'
MAX_BYTES=5_000_000


def capture_training_figure(source_folder,figure_id,expected_source_sha,expected_xml_sha,output):
    root=Path(source_folder).resolve();packet_bytes=(root/'source.json').read_bytes();packet=json.loads(packet_bytes)
    xml_bytes=(root/'article.xml').read_bytes();source=packet['source']
    require(source['sha256']==expected_source_sha==sha256(source['text'].encode()).hexdigest()
        and packet['raw_xml_sha256']==expected_xml_sha==sha256(xml_bytes).hexdigest(),'Published source revision differs')
    require(source['sha256']!='f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8',
        'Approved excluded target is not a training figure source')
    parser=ET.XMLParser(target=ET.TreeBuilder(insert_pis=True));article=ET.fromstring(xml_bytes,parser=parser)
    require(article.findtext(".//article-id[@pub-id-type='pmcid']")==packet['pmcid'].upper()
        and article.findtext(".//article-id[@pub-id-type='doi']")==packet['doi'],'Figure article identity differs')
    figures=[f for f in article.findall('.//fig')if f.get('id')==figure_id]
    require(len(figures)==1,'Exact published figure required');figure=figures[0]
    graphics=figure.findall('graphic');require(len(graphics)==1,'Explicit single Nature-style graphic required')
    graphic=graphics[0];metadata={}
    for node in graphic:
        if node.tag is ET.ProcessingInstruction:
            key,value=node.text.split(' ',1);require(key not in metadata,'Repeated image metadata');metadata[key]=value
    checksum=metadata['image-md5'];urn=metadata['image-cloudpmc-urn'];name=graphic.get('{http://www.w3.org/1999/xlink}href')
    require(re.fullmatch(r'[a-f0-9]{32}',checksum)and urn.startswith('urn:cdn:blobs/')and name
        and urn.endswith('/'+name)and re.fullmatch(r'[A-Za-z0-9_.-]+\.jpg',name),'Unsupported graphic binding')
    url='https://cdn.ncbi.nlm.nih.gov/pmc/'+urn.removeprefix('urn:cdn:')
    declared_size=int(metadata['image-size']);require(0<declared_size<=MAX_BYTES,'Unbounded published image')
    request=urllib.request.Request(url,headers={'User-Agent':'KnowledgeMap-source-audit/1','Accept':'image/jpeg'})
    with urllib.request.urlopen(request,timeout=30)as response:
        require(response.geturl()==url and response.headers.get_content_type()=='image/jpeg','Unexpected image redirect or type')
        data=response.read(MAX_BYTES+1)
    require(len(data)==declared_size and md5(data).hexdigest()==checksum,'Published graphic bytes differ from XML')
    descriptor={'version':VERSION,'pmcid':packet['pmcid'].upper(),'doi':packet['doi'],'figure_id':figure_id,
        'url':url,'image_name':name,'image_md5':checksum,'image_sha256':sha256(data).hexdigest(),'image_bytes':len(data),
        'source_sha256':expected_source_sha,'raw_xml_sha256':expected_xml_sha,'source_packet_sha256':sha256(packet_bytes).hexdigest(),
        'scaled_width':int(metadata['image-scaled-width']),'scaled_height':int(metadata['image-scaled-height']),
        'captured_at_utc':datetime.now(timezone.utc).isoformat(),'past_training_source':True,'target_read':False,
        'model_calls':0,'expert_validated':False,'visual_interpretation_supplied_by_capture':False,
        'adapter_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    folder=Path(output).resolve();write_immutable(folder/'image.jpg',data);write_immutable(folder/'article.xml',xml_bytes)
    write_immutable(folder/'source-packet.json',packet_bytes)
    write_immutable(folder/'acquisition.json',FilePredictionStore.encode(descriptor));return descriptor
