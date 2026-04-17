export const MARKDOWN_PREVIEW_STYLES = `
.km-md-preview h1 { font-size: 2em; font-weight: 700; margin: 0.67em 0; }
.km-md-preview h2 { font-size: 1.5em; font-weight: 700; margin: 0.75em 0; }
.km-md-preview h3 { font-size: 1.25em; font-weight: 700; margin: 0.83em 0; }
.km-md-preview h4 { font-size: 1em; font-weight: 700; margin: 1.12em 0; }
.km-md-preview p { margin: 0.8em 0; line-height: 1.6; }
.km-md-preview ul { list-style-type: disc; padding-left: 2em; margin: 0.8em 0; }
.km-md-preview ol { list-style-type: decimal; padding-left: 2em; margin: 0.8em 0; }
.km-md-preview li { margin: 0.3em 0; }
.km-md-preview strong { font-weight: 700; }
.km-md-preview em { font-style: italic; }
.km-md-preview code { background: #f4f4f4; padding: 2px 5px; border-radius: 3px; font-family: monospace; font-size: 0.9em; }
.km-md-preview pre { background: #f4f4f4; padding: 12px; border-radius: 4px; overflow-x: auto; margin: 0.8em 0; }
.km-md-preview pre code { background: none; padding: 0; }
.km-md-preview blockquote { border-left: 4px solid #ddd; padding-left: 1em; color: #666; margin: 0.8em 0; }
.km-md-preview a { color: #0066cc; text-decoration: underline; }
.km-md-preview img { max-width: 100%; height: auto; border-radius: 4px; margin: 8px 0; }
.km-md-preview figure { margin: 1.2em 0; text-align: center; }
.km-md-preview figure img { display: block; margin: 0 auto; }
.km-md-preview figcaption { font-size: 0.9em; color: #555; margin-top: 6px; font-style: italic; }
.km-md-preview table { border-collapse: collapse; width: 100%; margin: 0.8em 0; }
.km-md-preview th, .km-md-preview td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }
.km-md-preview th { background: #f5f5f5; font-weight: 700; }

.km-katex-wrap { position: relative; display: inline-block; }
.km-katex-wrap.block { display: block; text-align: center; margin: 0.8em 0; }
.km-katex-copy {
    display: none; position: absolute; top: -6px; right: -6px;
    background: #fff; border: 1px solid #ccc; border-radius: 4px;
    padding: 2px 6px; font-size: 11px; cursor: pointer; color: #555;
    white-space: nowrap; box-shadow: 0 1px 4px rgba(0,0,0,0.15);
    line-height: 1.4; z-index: 10;
}
.km-katex-wrap:hover .km-katex-copy { display: block; }
.km-katex-copy.copied { background: #e6f4ea; color: #2a7a3b; border-color: #a5d6a7; }
`;
