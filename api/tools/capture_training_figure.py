"""CLI архивирует уже просмотренный рисунок прошлого источника с проверкой контрольной суммы."""
import argparse
import json
from infrastructure.published_figure_capture import capture_training_figure


def main():
    p=argparse.ArgumentParser()
    for name in ('source-folder','figure-id','source-sha','xml-sha','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();result=capture_training_figure(a.source_folder,a.figure_id,a.source_sha,a.xml_sha,a.output)
    print(json.dumps({k:result[k]for k in ('pmcid','figure_id','image_sha256','image_bytes','model_calls','target_read')}))


if __name__=='__main__':main()
