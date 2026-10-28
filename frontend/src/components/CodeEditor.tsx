import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { cpp } from "@codemirror/lang-cpp";
import { bracketMatching, HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags } from "@lezer/highlight";
import { EditorState, StateEffect, StateField, type Extension } from "@codemirror/state";
import { Decoration, type DecorationSet, EditorView, keymap, lineNumbers } from "@codemirror/view";
import { useEffect, useRef } from "react";

export interface Marks { active: number[]; errors: number[]; dead: number[] }
const setMarks = StateEffect.define<Marks>();

const codeHighlight = HighlightStyle.define([
  { tag: tags.keyword, color: "#527260", fontWeight: "600" },
  { tag: [tags.typeName, tags.className], color: "#78623b" },
  { tag: [tags.string, tags.character], color: "#9a5b42" },
  { tag: [tags.number, tags.bool, tags.null], color: "#8b6426" },
  { tag: tags.comment, color: "#858d84", fontStyle: "italic" },
  { tag: [tags.function(tags.variableName), tags.definition(tags.variableName)], color: "#42634d" },
  { tag: tags.operator, color: "#68716a" },
]);

const marksField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(deco, tr) {
    deco = deco.map(tr.changes);
    for (const e of tr.effects) {
      if (!e.is(setMarks)) continue;
      const doc = tr.state.doc, items: { from: number; cls: string }[] = [];
      const add = (lines: number[], cls: string) => lines.forEach((l) => { if (l >= 1 && l <= doc.lines) items.push({ from: doc.line(l).from, cls }); });
      add(e.value.dead, "cm-dead-line"); add(e.value.active, "cm-active-line"); add(e.value.errors, "cm-error-line");
      items.sort((a, b) => a.from - b.from);
      deco = Decoration.set(items.map((i) => Decoration.line({ class: i.cls }).range(i.from)), true);
    }
    return deco;
  },
  provide: (f) => EditorView.decorations.from(f),
});

const theme = EditorView.theme({
  "&": { height: "100%", fontSize: "13px", backgroundColor: "var(--surface)", color: "var(--text)" },
  ".cm-scroller": { fontFamily: "var(--mono)", lineHeight: "1.55" },
  ".cm-gutters": { backgroundColor: "var(--surface-2)", color: "var(--muted)", border: "none", borderRight: "1px solid var(--border)" },
  ".cm-content": { caretColor: "var(--accent)" },
  "&.cm-focused": { outline: "none" },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": { backgroundColor: "var(--select-bg) !important" },
  ".cm-active-line": { backgroundColor: "var(--hl-bg)", boxShadow: "inset 3px 0 0 var(--accent)" },
  ".cm-error-line": { backgroundColor: "var(--danger-bg)", boxShadow: "inset 3px 0 0 var(--danger)" },
  ".cm-dead-line": { opacity: "0.55", textDecoration: "underline dotted var(--muted)" },
});

interface Props {
  value: string; onChange: (v: string) => void; marks: Marks;
  onSelectLines: (from: number, to: number) => void; onRun: () => void;
  scrollToLine?: { line: number; nonce: number } | null;
}

export default function CodeEditor({ value, onChange, marks, onSelectLines, onRun, scrollToLine }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const cb = useRef({ onChange, onSelectLines, onRun });
  cb.current = { onChange, onSelectLines, onRun };

  useEffect(() => {
    const ext: Extension[] = [
      lineNumbers(), history(), bracketMatching(), cpp(), syntaxHighlighting(codeHighlight),
      marksField, theme,
      keymap.of([{ key: "Mod-Enter", run: () => { cb.current.onRun(); return true; } }, indentWithTab, ...defaultKeymap, ...historyKeymap]),
      EditorView.updateListener.of((u) => {
        if (u.docChanged) cb.current.onChange(u.state.doc.toString());
        else if (u.selectionSet && u.transactions.some((t) => t.isUserEvent("select"))) {
          const s = u.state.selection.main;
          cb.current.onSelectLines(u.state.doc.lineAt(s.from).number, u.state.doc.lineAt(s.to).number);
        }
      }),
      EditorView.contentAttributes.of({ "aria-label": "C source code editor", spellcheck: "false" }),
    ];
    view.current = new EditorView({ state: EditorState.create({ doc: value, extensions: ext }), parent: host.current! });
    return () => view.current?.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const v = view.current;
    if (v && v.state.doc.toString() !== value) v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: value } });
  }, [value]);

  useEffect(() => { view.current?.dispatch({ effects: setMarks.of(marks) }); }, [marks]);

  useEffect(() => {
    const v = view.current;
    if (!v || !scrollToLine || scrollToLine.line < 1 || scrollToLine.line > v.state.doc.lines) return;
    v.dispatch({ effects: EditorView.scrollIntoView(v.state.doc.line(scrollToLine.line).from, { y: "center" }) });
  }, [scrollToLine]);

  return <div className="editor-host" ref={host} data-testid="code-editor" />;
}
