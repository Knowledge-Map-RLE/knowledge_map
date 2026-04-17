import type { Annotation, AnnotationRelation } from '../entities/annotation';

function csvEscape(value: string): string {
  const str = String(value ?? '');
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return '"' + str.replace(/"/g, '""') + '"';
  }
  return str;
}

function csvParseLine(line: string): string[] {
  const result: string[] = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        current += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        current += ch;
      }
    } else {
      if (ch === '"') {
        inQuotes = true;
      } else if (ch === ',') {
        result.push(current);
        current = '';
      } else {
        current += ch;
      }
    }
  }
  result.push(current);
  return result;
}

export function buildAnnotationsCSV(annotations: Annotation[], relations: AnnotationRelation[]): string {
  const annHeader = 'uid,text,annotation_type,start_offset,end_offset,color,source,confidence';
  const annRows = annotations.map(a =>
    [
      csvEscape(a.uid),
      csvEscape(a.text),
      csvEscape(a.annotation_type),
      a.start_offset,
      a.end_offset,
      csvEscape(a.color),
      csvEscape(a.source ?? ''),
      a.confidence ?? '',
    ].join(',')
  );
  const relHeader = 'relation_uid,source_uid,target_uid,relation_type';
  const relRows = relations.map(r =>
    [
      csvEscape(r.relation_uid),
      csvEscape(r.source_uid),
      csvEscape(r.target_uid),
      csvEscape(r.relation_type),
    ].join(',')
  );
  return ['# ANNOTATIONS', annHeader, ...annRows, '# RELATIONS', relHeader, ...relRows].join('\n');
}

export function parseAnnotationsCSV(csvText: string): {
  annotations: Partial<Annotation>[];
  relations: Partial<AnnotationRelation>[];
} {
  const lines = csvText.split('\n').map(l => l.trimEnd());
  let section: 'none' | 'annotations' | 'relations' = 'none';
  let annHeaders: string[] = [];
  let relHeaders: string[] = [];
  const annotations: Partial<Annotation>[] = [];
  const relations: Partial<AnnotationRelation>[] = [];

  for (const line of lines) {
    if (line === '# ANNOTATIONS') { section = 'annotations'; annHeaders = []; continue; }
    if (line === '# RELATIONS') { section = 'relations'; relHeaders = []; continue; }
    if (!line || line.startsWith('#')) continue;

    if (section === 'annotations') {
      if (annHeaders.length === 0) { annHeaders = csvParseLine(line); continue; }
      const vals = csvParseLine(line);
      const obj: Partial<Annotation> = {};
      annHeaders.forEach((h, i) => {
        const v = vals[i] ?? '';
        if (h === 'start_offset') obj.start_offset = parseInt(v, 10);
        else if (h === 'end_offset') obj.end_offset = parseInt(v, 10);
        else if (h === 'confidence') obj.confidence = v !== '' ? parseFloat(v) : undefined;
        else (obj as any)[h] = v;
      });
      if (obj.text !== undefined) annotations.push(obj);
    } else if (section === 'relations') {
      if (relHeaders.length === 0) { relHeaders = csvParseLine(line); continue; }
      const vals = csvParseLine(line);
      const obj: Partial<AnnotationRelation> = {};
      relHeaders.forEach((h, i) => { (obj as any)[h] = vals[i] ?? ''; });
      if (obj.source_uid && obj.target_uid) relations.push(obj);
    }
  }

  return { annotations, relations };
}
