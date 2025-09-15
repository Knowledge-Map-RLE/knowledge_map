import React, { useEffect, useMemo, useRef, useState } from 'react';

type Props = {
  docId: string;
  markdown: string;
  images: string[];
  imageUrls?: Record<string,string>;
  onExport: (json: any) => void;
  onImport: (json: any) => void;
};

type Annotation = {
  id: number;
  label: string;
  text: string;
};

const LABELS = [
  'Organization','Person','Disease','Drug','Treatment','Datetime','Gene','Protein'
];

export default function MarkdownAnnotator({ docId, markdown, images, imageUrls, onExport, onImport }: Props) {
  const [selectedLabel, setSelectedLabel] = useState<string>('');
  const [annotations, setAnnotations] = useState<Annotation[]>([]);

  const html = useMemo(() => {
    // заменим картинки на теги img (имена без путей) — клиент их не грузит с S3 напрямую
    const md = markdown || '';
    const withImgs = md.replace(/!\[[^\]]*\]\(([^)]+)\)/g, (_m, p1) => {
      const fname = String(p1).split('/').pop() as string;
      const url = (imageUrls && imageUrls[fname]) ? imageUrls[fname] : fname;
      return `<img src="${url}" alt="" style="max-width:100%;height:auto;border-radius:8px;margin:12px 0;"/>`;
    });
    const p = withImgs
      .replace(/^# (.*)$/gm, '<h1>$1</h1>')
      .replace(/^## (.*)$/gm, '<h2>$1</h2>')
      .replace(/^### (.*)$/gm, '<h3>$1</h3>')
      .replace(/\n\n+/g, '</p><p>');
    return `<p>${p}</p>`;
  }, [markdown, imageUrls]);

  useEffect(() => {
    setAnnotations([]);
  }, [docId]);

  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = () => {
      if (!selectedLabel) return;
      const sel = window.getSelection();
      const text = sel?.toString().trim();
      if (!text) return;
      try {
        const range = sel!.getRangeAt(0);
        const span = document.createElement('span');
        span.className = 'annotation-chip';
        span.style.background = 'rgba(102,126,234,0.2)';
        span.style.borderRadius = '4px';
        span.style.padding = '2px 4px';
        span.style.cursor = 'pointer';
        span.textContent = text;
        range.deleteContents();
        range.insertNode(span);
        sel?.removeAllRanges();
        setAnnotations(prev => [ ...prev, { id: Date.now(), label: selectedLabel, text } ]);
      } catch { /* noop */ }
    };
    document.addEventListener('mouseup', handler);
    return () => document.removeEventListener('mouseup', handler);
  }, [selectedLabel]);

  const doExport = () => onExport({ doc_id: docId, annotations });

  const handleImport = async (ev: React.ChangeEvent<HTMLInputElement>) => {
    const f = ev.target.files?.[0];
    if (!f) return;
    try {
      const txt = await f.text();
      const data = JSON.parse(txt);
      onImport(data);
    } catch {/* noop */}
  };

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:12, height:'100%' }}>
      <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
        {LABELS.map(l => (
          <button key={l} onClick={() => setSelectedLabel(l)} style={{
            padding:'8px 12px', border:'0', borderRadius:6, cursor:'pointer',
            background: selectedLabel===l ? '#667eea' : '#95a5a6', color:'#fff'
          }}>{l}</button>
        ))}
        <button onClick={doExport} style={{ padding:'8px 12px', border:'0', borderRadius:6, background:'#27ae60', color:'#fff' }}>
          Экспорт аннотаций
        </button>
        <label style={{ padding:'8px 12px', borderRadius:6, background:'#f39c12', color:'#fff', cursor:'pointer' }}>
          Импорт аннотаций
          <input type="file" accept="application/json" onChange={handleImport} style={{ display:'none' }} />
        </label>
      </div>
      <div ref={contentRef} className="markdown-annotator" style={{ overflow:'auto', flex:'1 1 auto', background:'#fff', borderRadius:8, padding:16 }}
           dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  );
}


