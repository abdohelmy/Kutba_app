"use client";
import { useState, useEffect, useRef } from "react";
import {useLiveScroll} from "@/lib/use-live-scroll";
import {getLive,LiveHighlight,LiveState,liveStatus} from "@/lib/live";
import {glossaryHeading} from '@/lib/glossary-heading';
import { Download, Bookmark, Share2, Search } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sermon,
  Term,
  Citation,
  Segment,
  safeURL,
  dateLabel,
  storage,
  saveLocal,
} from "@/lib/khutba";
type Note = { kind: "term"; value: Term } | { kind: "source"; value: Citation };
function passage(segment: Segment, onNote: (n: Note) => void, query: string, language: string, live:LiveHighlight[]=[]) {
  const chars = Array.from(segment.translated_text || "");
  const source = chars.join("");
  const events: {
    start: number;
    end: number;
    term?: Term;
    source?: Citation;
  }[] = [];
  const highlights=live.filter(h=>h.segment_id===segment.id&&h.start>=0&&h.end>h.start&&h.end<=source.length&&source.slice(h.start,h.end)===h.excerpt).map(h=>({start:Array.from(source.slice(0,h.start)).length,end:Array.from(source.slice(0,h.end)).length,tentative:h.tentative,basis:h.basis}));
  for(const range of highlights){events.push({start:range.start,end:range.start});events.push({start:range.end,end:range.end});}
  const active=(start:number,end:number)=>highlights.some(h=>!h.tentative&&h.start<end&&h.end>start);
  const uncertain=(start:number,end:number)=>!active(start,end)&&highlights.some(h=>h.tentative&&h.start<end&&h.end>start);
  const highlightClass=(start:number,end:number)=>active(start,end)?"live-highlight":uncertain(start,end)?(
    highlights.some(h=>h.tentative&&h.basis!=="timer"&&h.start<end&&h.end>start)
      ?"live-highlight-tentative":"live-highlight-tentative live-highlight-estimated"
  ):"";
  for (const t of segment.glossary_terms || []) {
    const start = t.translation_start,
      end = t.translation_end;
    if (
      start !== undefined &&
      end !== undefined &&
      start >= 0 &&
      end > start &&
      chars.slice(start, end).join("") === t.arabic_term
    )
      events.push({ start, end, term: t });
  }
  for (const c of segment.citations || []) {
    const start = c.translation_start,
      end = c.translation_end;
    if (
      c.anchor_valid !== false &&
      start !== undefined &&
      end !== undefined &&
      start >= 0 &&
      end > start &&
      chars.slice(start, end).join("") === c.excerpt
    )
      events.push({ start: end, end, source: c });
  }
  events.sort((a, b) => a.start - b.start || a.end - b.end);
  let cursor = 0;
  const nodes: React.ReactNode[] = [];
  const plain = (s: string, key: string, offset:number) => {
    const current=active(offset,offset+Array.from(s).length);
    const className=highlightClass(offset,offset+Array.from(s).length);
    if (!query.trim()) return <span key={key} className={className} data-live-highlight={current||undefined}>{s}</span>;
    const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return (
      <span key={key} className={className} data-live-highlight={current||undefined}>
        {s
          .split(new RegExp(`(${escaped})`, "gi"))
          .map((p, i) =>
            p.toLowerCase() === query.toLowerCase() ? (
              <mark key={i}>{p}</mark>
            ) : (
              p
            ),
          )}
      </span>
    );
  };
  for (const [i, e] of events.entries()) {
    if (e.start < cursor) continue;
    nodes.push(plain(chars.slice(cursor, e.start).join(""), `p${i}`,cursor));
    if (e.term)
      nodes.push(
        <button
          className={"term-link "+highlightClass(e.start,e.end)}
          data-live-highlight={active(e.start,e.end)||undefined}
          key={`t${i}`}
          dir="rtl"
          onClick={() => onNote({ kind: "term", value: {
            ...e.term!, popup_phrase:glossaryHeading(source,e.term!,language),popup_language:language,
          } })}
        >
          {e.term.arabic_term}
        </button>,
      );
    if (e.source)
      nodes.push(
        <button
          className="citation-link"
          key={`c${i}`}
          aria-label={`Source: ${e.source.display_reference || e.source.title}`}
          onClick={() => onNote({ kind: "source", value: e.source! })}
        >
          ▣
        </button>,
      );
    cursor = e.end;
  }
  nodes.push(plain(chars.slice(cursor).join(""), "last",cursor));
  return <>{nodes.length ? nodes : source}</>;
}
export function Reader({
  sermon,
  preview = false,
  offline = false,
  onError,
}: {
  sermon: Sermon;
  preview?: boolean;
  offline?: boolean;
  onError: (s: string) => void;
}) {
  const [note, setNote] = useState<Note | null>(null),
    [size, setSize] = useState(20),
    [query, setQuery] = useState(""),
    [saved, setSaved] = useState(false),
    [position, setPosition] = useState(0);
  const [live,setLive]=useState<LiveState>(),[follow,setFollow]=useState(false),[autoScroll,setAutoScroll]=useState(true);
  const article=useRef<HTMLElement>(null);
  useEffect(()=>{if(preview||offline)return;let cancelled=false,timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{try{if(document.visibilityState!=="hidden"){const state=await getLive(sermon.id);if(!cancelled)setLive(state);}}catch{if(!cancelled)setLive(old=>old?{...old,status:"worker_offline"}:undefined);}finally{if(!cancelled)timer=setTimeout(poll,follow?1000:6000);}};
    void poll();return()=>{cancelled=true;clearTimeout(timer);};
  },[sermon.id,follow,preview,offline]);
  const liveSignature=JSON.stringify(live?.highlights||[]);
  useLiveScroll(article,liveSignature,follow&&autoScroll&&Boolean(live?.active),Boolean(note),()=>setAutoScroll(false),size);
  useEffect(()=>{setFollow(false);setAutoScroll(true);setLive(undefined);},[sermon.id]);
  useEffect(() => {
    setSize(storage("text-size", 20));
    setSaved(Boolean(storage<Record<string, Sermon>>("saved", {})[sermon.id]));
    setPosition(storage<number>("position:" + sermon.id, 0));
  }, [sermon.id]);
  function toggleSave() {
    try {
      const all = storage<Record<string, Sermon>>("saved", {});
      if (saved) delete all[sermon.id];
      else all[sermon.id] = sermon;
      saveLocal("saved", all);
      setSaved(!saved);
    } catch (e) {
      onError((e as Error).message);
    }
  }
  async function share() {
    try {
      const url = new URL(location.href);
      url.hash = "read/" + sermon.id;
      if (navigator.share)
        await navigator.share({ title: sermon.title, url: url.href });
      else {
        await navigator.clipboard.writeText(url.href);
        onError("Link copied.");
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError")
        onError(
          "Could not share this link. You can copy the address from your browser.",
        );
    }
  }
  return (
    <>
      <div className="reader-heading">
        <div className="eyebrow">
          {dateLabel(sermon.khutba_date)}
          {sermon.target_language === "da" ? " · Dansk" : " · English"}
          {preview ? " · Preview" : ""}
        </div>
        <h1>{sermon.title}</h1>
        {offline && (
          <p role="status" className="notice">
            Saved copy · You’re offline. This may not be the latest version.
          </p>
        )}
        {!preview&&!offline&&live?.active&&<div className="live-reader-controls"><p role="status">{liveStatus(live)} · approximate position</p><div className="actions"><Button variant={follow?"outline":"default"} onClick={()=>{setFollow(!follow);setAutoScroll(true);}}>{follow?"Stop following":"Follow imam"}</Button></div></div>}
      </div>
      {follow&&live?.active&&<div className="live-follow-bar" aria-label="Live reading controls"><span>{autoScroll?(live.provisional?"Finding position":"Following live"):"Scrolling paused"}</span><Button variant="outline" onClick={()=>setAutoScroll(!autoScroll)}>{autoScroll?"Pause scrolling":"Return to live"}</Button></div>}
      <div className="reader-layout">
        <aside className="reading-tools">
          <h2 className="small-heading">Reading</h2>
          <label htmlFor="sermon-search">Find in khutba</label>
          <div className="search-row">
            <Search size={18} />
            <Input
              id="sermon-search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search this text"
            />
          </div>
          <label>Text size</label>
          <Slider
            aria-label="Reading text size"
            min={17}
            max={30}
            step={1}
            value={[size]}
            onValueChange={(v) => {
              setSize(v[0]);
              try {
                saveLocal("text-size", v[0]);
              } catch {}
            }}
          />
          <p className="muted">
            Tap an Arabic word for its meaning. Tap ▣ to check a source.
          </p>
          {!preview && (
            <>
              <Button variant="outline" onClick={toggleSave}>
                <Bookmark size={18} />
                {saved ? "Remove saved copy" : "Save for offline"}
              </Button>
              <Button variant="outline" onClick={share}>
                <Share2 size={18} />
                Share khutba
              </Button>
              <a
                className="button-link"
                href={`/api/reader/sermons/${sermon.id}/pdf`}
                target="_blank"
                rel="noopener"
              >
                <Download size={18} />
                Download PDF
              </a>
            </>
          )}
          {position > 0 && (
            <Button
              variant="outline"
              onClick={() =>
                document
                  .getElementById("segment-" + position)
                  ?.scrollIntoView({ behavior: "smooth" })
              }
            >
              Continue reading
            </Button>
          )}
        </aside>
        <article
          ref={article}
          className="sermon-text"
          style={{ fontSize: `${size / 16}rem` }}
        >
          {(sermon.segments || []).map((segment, i) => (
            <section id={`segment-${i}`} key={segment.id}>
              <p>{passage(segment, setNote, query, sermon.target_language || 'en',follow&&live?.active?[...live.highlights,...(live.tentative_highlights||[]).map(h=>({...h,tentative:true}))]:[])}</p>
              <button
                className="bookmark-line"
                onClick={() => {
                  try {
                    saveLocal("position:" + sermon.id, i);
                    setPosition(i);
                  } catch (e) {
                    onError((e as Error).message);
                  }
                }}
              >
                <Bookmark size={14} />
                Mark this place
              </button>
            </section>
          ))}
          {(sermon.segments || []).some((s) => s.citations?.length > 0) && (
            <details className="source-list">
              <summary>Sources</summary>
              {sermon.segments
                ?.flatMap((s) => s.citations || [])
                .map((c, i) => (
                  <button
                    key={i}
                    onClick={() => setNote({ kind: "source", value: c })}
                  >
                    {c.display_reference || c.title}
                  </button>
                ))}
            </details>
          )}
        </article>
      </div>
      <Dialog open={!!note} onOpenChange={(v) => !v && setNote(null)}>
        <DialogContent className="note-panel">
          <DialogTitle>
            {note?.kind === "term"
              ? note.value.popup_phrase || (sermon.target_language==='da'?'Ordforklaring':'Word meaning')
              : note?.value.display_reference || note?.value.title}
          </DialogTitle>
          <DialogDescription>
            {note?.kind === "term"
              ? "Word meaning"
              : "Original wording and source"}
          </DialogDescription>
          {note && (
            <>
              <p className="arabic-note" dir="rtl" lang="ar">
                {note.kind === "term"
                  ? note.value.arabic_term
                  : note.value.arabic_excerpt}
              </p>
              {note.value.transliteration && (
                <div>
                  <p>{note.value.transliteration}</p>
                  {note.kind === "term" && (
                    <small>
                      Letter transliteration · vowels may be incomplete
                    </small>
                  )}
                </div>
              )}
              {note.kind === "term" ? (
                <>
                  <p>{note.value.meaning}</p>
                  {note.value.alternative_context_meanings && (
                    <>
                      <h3>Other contexts</h3>
                      <p>{note.value.alternative_context_meanings}</p>
                    </>
                  )}
                </>
              ) : (
                <>
                  <p>{note.value.authority}</p>
                  {sermon.target_language === "da" && <p className="muted">Dansk gengivelse, gennemgået af moskeen. Kilden dokumenterer den arabiske tekst og den engelske oversættelse.</p>}
                  {safeURL(note.value.url) && (
                    <a
                      className="button-link"
                      href={safeURL(note.value.url)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Open source
                    </a>
                  )}
                </>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
