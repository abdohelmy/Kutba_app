"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { moveAlignment, selectedArabic, SentenceAlignment } from "@/lib/sentence-alignment";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from "@/components/ui/alert-dialog";
import { Reader } from "./khutba-reader";
import {LiveAdmin} from "./live-admin";
import {
  api,
  Candidate,
  Glossary,
  Mosque,
  Segment,
  Sermon,
  Term,
  dateLabel,
  friday,
} from "@/lib/khutba";
type Props = { go: (path: string) => void; notify: (message: string) => void };
function Field({
  label,
  name,
  type = "text",
  value,
  onChange,
  required = true,
  minLength,
}: {
  label: string;
  name: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  minLength?: number;
}) {
  return (
    <label className="field">
      {label}
      <Input
        name={name}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        minLength={minLength}
        autoComplete={
          type === "password"
            ? name === "password"
              ? "current-password"
              : "new-password"
            : name === "username"
              ? "username"
              : "off"
        }
      />
    </label>
  );
}
export function Auth({ go, notify }: Props) {
  const [register, setRegister] = useState(false),
    [busy, setBusy] = useState(false),
    [values, setValues] = useState<Record<string, string>>({ country: "DK" });
  const field = (
    name: string,
    label: string,
    type = "text",
    minLength?: number,
  ) => (
    <Field
      key={name}
      {...{ name, label, type, minLength }}
      value={values[name] || ""}
      onChange={(v) => setValues({ ...values, [name]: v })}
    />
  );
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      if (register) {
        await api("auth/register-mosque", "POST", values);
        setRegister(false);
        notify("Request submitted. You can sign in once the app owner approves your mosque.");
        return;
      }
      await api("auth/login", "POST", {
        username: values.username,
        password: values.password,
        account_type: "MOSQUE",
      });
      const user = await api<{role:string}>("auth/me");
      go(user.role === "SUPER_ADMIN" ? "owner" : "admin");
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel auth-panel">
      <div className="eyebrow">Mosque workspace</div>
      <h1>{register ? "Create a mosque profile" : "Welcome back"}</h1>
      <p className="muted">
        {register
          ? "Your mosque will be reviewed by the app owner before you can publish."
          : "Sign in to prepare and publish your khutbas."}
      </p>
      <form onSubmit={submit}>
        {register && (
          <>
            {field("mosque_name", "Mosque name", "text", 2)}
            {field("city", "City", "text", 2)}
            {field("country", "Country code (e.g. DK)", "text", 2)}
            {field("admin_display_name", "Your name", "text", 2)}
            {field("contact_email", "Contact email", "email")}
          </>
        )}
        {field("username", "Username", "text", 3)}
        {field("password", "Password", "password", register ? 6 : undefined)}
        <Button disabled={busy} type="submit">
          {busy ? "Please wait…" : register ? "Create profile" : "Sign in"}
        </Button>
      </form>
      {!register && <Button variant="ghost" onClick={() => go("recovery")}>Forgot password?</Button>}
      <Button
        variant="ghost"
        disabled={busy}
        onClick={() => setRegister(!register)}
      >
        {register
          ? "Already have a profile? Sign in"
          : "Create a mosque profile"}
      </Button>
    </section>
  );
}
export function Admin({ go, notify }: Props) {
  const [items, setItems] = useState<Sermon[]>([]),
    [loading, setLoading] = useState(true),
    [upload, setUpload] = useState(false),
    [busy, setBusy] = useState(false),
    [remove, setRemove] = useState<Sermon | null>(null);
  const refresh=useCallback(async()=> {
    try {
      setItems(await api<Sermon[]>("admin/sermons"));
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setLoading(false);
    }
  },[notify]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const file = data.get("file") as File;
    if (!file || file.size > 15 * 1024 * 1024) {
      notify("Choose a PDF or DOCX smaller than 15 MB.");
      return;
    }
    data.set("target_language", "en");
    setBusy(true);
    try {
      const item = await api<Sermon>("admin/sermons", "POST", data);
      go("review/" + item.id);
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function action(item: Sermon, name: string) {
    setBusy(true);
    try {
      await api(
        `admin/sermons/${item.id}${name === "delete" ? "" : "/" + name}`,
        name === "delete" ? "DELETE" : "POST",
      );
      setRemove(null);
      await refresh();
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">Mosque workspace</div>
          <h1>Your khutbas</h1>
        </div>
        <div className="actions">
          <Button variant="outline" onClick={() => go("settings")}>
            Settings & glossary
          </Button>
          <Button onClick={() => setUpload(!upload)}>Upload khutba</Button>
        </div>
      </div>
      {upload && (
        <section className="panel">
          <h2>Prepare a khutba</h2>
          <form onSubmit={submit} className="form-grid">
            <label className="field">
              PDF or Word document
              <Input
                name="file"
                type="file"
                accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                required
              />
            </label>
            <label className="field">
              Khutba date
              <Input
                type="date"
                name="khutba_date"
                defaultValue={friday()}
                required
              />
            </label>
            <label className="field">
              Title (optional)
              <Input
                name="title"
                placeholder="Leave blank to infer from the khutba"
              />
            </label>
            <p className="muted">
              Arabic text is extracted before translation. You can check and
              correct it next.
            </p>
            <Button disabled={busy}>
              {busy ? "Extracting text…" : "Upload & check text"}
            </Button>
          </form>
        </section>
      )}
      {loading ? (
        <p role="status">Loading your khutbas…</p>
      ) : items.length === 0 ? (
        <div className="empty">
          No khutbas yet. Upload your first document to get started.
        </div>
      ) : (
        <div className="stack">
          {items.map((item) => (
            <section className="panel khutba-row" key={item.id}>
              <div>
                <div className="eyebrow">
                  {dateLabel(item.khutba_date)} ·{" "}
                  {item.target_language === "da" ? "Dansk" : "English"} ·{" "}
                  {item.status.replaceAll("_", " ").toLowerCase()}
                </div>
                <h2>{item.title}</h2>
              </div>
              <div className="actions">
                <Button
                  variant="outline"
                  onClick={() => go("review/" + item.id)}
                >
                  Open
                </Button>
                {item.status === "PUBLISHED" && item.target_language !== "da" && (
                  <Button variant="outline" disabled={busy} onClick={async () => {
                    setBusy(true);
                    try {
                      const child = await api<Sermon>(`admin/sermons/${item.id}/danish`, "POST");
                      go("review/" + child.id);
                    } catch (e) { notify((e as Error).message); }
                    finally { setBusy(false); }
                  }}>Danish translation</Button>
                )}
                {["PUBLISHED", "HIDDEN"].includes(item.status) && (
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() =>
                      action(item, item.status === "HIDDEN" ? "show" : "hide")
                    }
                  >
                    {item.status === "HIDDEN"
                      ? "Show to readers"
                      : "Hide from readers"}
                  </Button>
                )}
                <Button
                  variant="ghost"
                  disabled={busy}
                  className="danger"
                  onClick={() => setRemove(item)}
                >
                  Remove
                </Button>
              </div>
            </section>
          ))}
        </div>
      )}
      <AlertDialog open={!!remove} onOpenChange={(v) => !v && setRemove(null)}>
        <AlertDialogContent>
          <AlertDialogTitle>Remove this khutba?</AlertDialogTitle>
          <AlertDialogDescription>
            “{remove?.title}” will be permanently deleted. Use Hide instead if
            you may want to show it again.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Keep khutba</AlertDialogCancel>
            <AlertDialogAction
              disabled={busy}
              onClick={(e) => {
                e.preventDefault();
                if (remove) void action(remove, "delete");
              }}
            >
              Remove permanently
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
function ReviewSegment({
  segment,
  id,
  onSaved,
  notify,
  readOnly,
  onDirty,
  language,
}: {
  segment: Segment;
  id: string;
  onSaved: () => void;
  notify: Props["notify"];
  readOnly: boolean;
  onDirty: (id:string,dirty:boolean)=>void;
  language?: string;
}) {
  const [text, setText] = useState(segment.translated_text || ""),
    [definitions, setDefinitions] = useState<Term[]>(language==='da' ? segment.localized_glossary || [] : []),
    [note, setNote] = useState(segment.reviewer_note || ""),
    [busy, setBusy] = useState(false);
  const [links, setLinks] = useState<SentenceAlignment[]>([]);
  const [selection, setSelection] = useState<[number, number]>([0, 0]);
  const [aligning, setAligning] = useState(false);
  const [alignmentStatus, setAlignmentStatus] = useState("");
  const textRef = useRef(text);
  const alignmentRequested = useRef(false);
  const sourceRef = useRef<HTMLParagraphElement>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);
  useEffect(()=>{
    const editor=editorRef.current;
    const update=()=>{
      if(editor && document.activeElement===editor) setSelection([editor.selectionStart,editor.selectionEnd]);
    };
    editor?.addEventListener("select",update);
    document.addEventListener("selectionchange",update);
    return ()=>{
      editor?.removeEventListener("select",update);
      document.removeEventListener("selectionchange",update);
    };
  },[]);
  const selected = selectedArabic(links, selection[0], selection[1], text.length);
  const activeRanges = selected.sort((a,b)=>a.start-b.start).reduce<{start:number,end:number}[]>((ranges, range)=>{
    const previous=ranges.at(-1);
    if(previous && range.start<=previous.end) previous.end=Math.max(previous.end,range.end);
    else ranges.push({...range});
    return ranges;
  },[]);
  async function loadAlignment() {
    if(aligning) return;
    alignmentRequested.current=true;
    const snapshot=textRef.current;
    setAligning(true);setAlignmentStatus("Finding the matching Arabic sentences…");
    try {
      const result=await api<SentenceAlignment[]>(`admin/sermons/${id}/segments/${segment.id}/alignment`,"POST",{translated_text:snapshot});
      setLinks(moveAlignment(result,snapshot,textRef.current));
      setAlignmentStatus(result.length ? "" : "No matching Arabic sentences found.");
    } catch {
      setAlignmentStatus("Arabic highlighting could not load. You can keep editing or retry.");
    } finally {setAligning(false);}
  }
  useEffect(()=>{
    const source=sourceRef.current, mark=source?.querySelector("mark");
    if(source && mark) source.scrollTop=mark.offsetTop-source.clientHeight/3;
  },[selection,links]);
  useEffect(() => {
    setText(segment.translated_text || "");
    textRef.current=segment.translated_text || "";
    setLinks([]);alignmentRequested.current=false;
    setNote(segment.reviewer_note || "");
    setDefinitions(language==='da' ? segment.localized_glossary || [] : []);
  }, [segment.translated_text, segment.reviewer_note, segment.localized_glossary, language]);
  const definitionsDirty = language==='da' && JSON.stringify(definitions) !== JSON.stringify(segment.localized_glossary || []);
  useEffect(()=>{onDirty(segment.id,definitionsDirty||text!==(segment.translated_text||"")||note!==(segment.reviewer_note||""));},[text,note,definitionsDirty,segment.id,segment.translated_text,segment.reviewer_note,onDirty]);
  async function save(approved: boolean) {
    setBusy(true);
    try {
      await api(`admin/sermons/${id}/segments/${segment.id}`, "PATCH", {
        translated_text: text,
        reviewer_note: note,
        approved,
        ...(language === "da" ? {localized_definitions: definitions.map(t => ({arabic_term:t.arabic_term, localized_phrase:t.localized_phrase, meaning:t.meaning}))} : {}),
      });
      onSaved();
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel review-segment">
      <div className="eyebrow">
        Passage {segment.ordinal + 1} ·{" "}
        {segment.verification_status?.replaceAll("_", " ").toLowerCase()}
      </div>
      <div className="review-columns">
        <div>
          {segment.english_text && <><h3>Approved English</h3><p style={{whiteSpace:"pre-wrap"}}>{segment.english_text}</p></>}
          <h3>Original Arabic</h3>
          <p className="source-arabic editing-source" lang="ar" dir="rtl" ref={sourceRef}>
            {activeRanges.length ? <>{activeRanges.map((range,index)=> <span key={`${range.start}-${range.end}`}>
              {(segment.arabic_text || "").slice(index ? activeRanges[index-1].end : 0,range.start)}
              <mark className="source-sentence">{(segment.arabic_text || "").slice(range.start,range.end)}</mark>
            </span>)}{(segment.arabic_text || "").slice(activeRanges.at(-1)!.end)}</> : segment.arabic_text}
          </p>
        </div>
        <div>
          <label className="field">
            {language === "da" ? "Danish translation" : "English translation"}
            <Textarea
              readOnly={readOnly}
              value={text}
              rows={12}
              ref={editorRef}
              onFocus={()=>{if(!alignmentRequested.current) void loadAlignment();}}
              onSelect={e=>setSelection([e.currentTarget.selectionStart,e.currentTarget.selectionEnd])}
              onChange={(e) => {
                const value=e.target.value, before=textRef.current;
                setLinks(previous=>moveAlignment(previous,before,value));
                textRef.current=value;setText(value);
                setSelection([e.target.selectionStart,e.target.selectionEnd]);
              }}
            />
          </label>
          {alignmentRequested.current && <div className="alignment-help">
            <span role="status">{alignmentStatus || (activeRanges.length ? "Matching Arabic highlighted" : "No Arabic match for this sentence")}</span>
            <Button type="button" variant="ghost" size="sm" disabled={aligning} onClick={()=>void loadAlignment()}>Refresh highlights</Button>
          </div>}
          {!!activeRanges.length && <p className="active-arabic-mobile source-arabic" lang="ar" dir="rtl">
            {activeRanges.map(range=>(segment.arabic_text || "").slice(range.start,range.end)).join(" … ")}
          </p>}
          <label className="field">
            Review note (optional)
            <Textarea readOnly={readOnly} value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
        </div>
      </div>
      {definitions.map((term, index) => <div className="field" key={term.arabic_term}>
        <h3>{term.english_phrase} · <span lang="ar" dir="rtl">{term.arabic_term}</span></h3>
        <label>Danish phrase<Input readOnly={readOnly} value={term.localized_phrase || ""} onChange={e => setDefinitions(definitions.map((t,i) => i === index ? {...t, localized_phrase:e.target.value} : t))}/></label>
        <label>Danish meaning<Textarea readOnly={readOnly} value={term.meaning} onChange={e => setDefinitions(definitions.map((t,i) => i === index ? {...t, meaning:e.target.value} : t))}/></label>
      </div>)}
      {!!segment.issues?.length && (
        <details>
          <summary>Translation checks ({segment.issues.length})</summary>
          <ul>
            {segment.issues.map((issue, i) => (
              <li key={i}>
                {typeof issue === "string" ? issue : JSON.stringify(issue)}
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="actions">
        <Button
          variant="outline"
          disabled={readOnly || busy || !text.trim()}
          onClick={() => save(false)}
        >
          Save changes
        </Button>
        <Button disabled={readOnly || busy || !text.trim()} onClick={() => save(true)}>
          {busy ? "Saving…" : "Save & approve passage"}
        </Button>
      </div>
    </section>
  );
}
function TitleEditor({item, onSaved, notify}: {item:Sermon; onSaved:(title:string)=>void; notify:Props["notify"]}) {
  const [title, setTitle] = useState(item.title);
  const [saving, setSaving] = useState(false);
  useEffect(() => setTitle(item.title), [item.id, item.title]);
  return <form className="panel" onSubmit={async e => {
    e.preventDefault(); setSaving(true);
    try {
      const result = await api<Sermon>(`admin/sermons/${item.id}/title`, "PATCH", {title:title.trim()});
      onSaved(result.title); notify("Title updated.");
    } catch(e) { notify((e as Error).message); }
    finally { setSaving(false); }
  }}>
    <label className="field">Khutba title<Input value={title} onChange={e=>setTitle(e.target.value)} required maxLength={250} disabled={saving || item.status === "TRANSLATING"}/></label>
    <Button type="submit" disabled={saving || item.status === "TRANSLATING" || !title.trim() || title.trim() === item.title}>{saving ? "Saving…" : "Save title"}</Button>
  </form>;
}

export function Review({ id, go, notify }: Props & { id: string }) {
  const [item, setItem] = useState<Sermon | null>(null),
    [source, setSource] = useState(""),
    [busy, setBusy] = useState(false),
    [preview, setPreview] = useState<Sermon | null>(null),
    [confirm, setConfirm] = useState(false),
    [pollError, setPollError] = useState(false);
  const [dirty,setDirty]=useState<Record<string,boolean>>({});
  const onDirty=useCallback((id:string,value:boolean)=>setDirty(old=>old[id]===value?old:{...old,[id]:value}),[]);
  const unsaved=Object.values(dirty).some(Boolean);
  const refresh=useCallback(async()=> {
    try {
      const s = await api<Sermon>("admin/sermons/" + id);
      setItem(s);
      setSource(s.segments?.map((v) => v.arabic_text || "").join("\n\n") || "");
      setPollError(false);
    } catch (e) {
      setPollError(true);
      notify((e as Error).message);
    }
  },[id,notify]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  useEffect(() => {
    if (item?.status !== "TRANSLATING" || pollError) return;
    const timer = setTimeout(() => void refresh(), 4000);
    return () => clearTimeout(timer);
  }, [item, pollError,refresh]);
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!item)
    return (
      <>
        <p role="status">
          {pollError ? "The khutba could not be loaded." : "Loading khutba…"}
        </p>
        {pollError && <Button onClick={refresh}>Try again</Button>}
      </>
    );
  const segments = item.segments || [],
    done = segments.filter((s) => s.translated_text).length,
    approved =
      segments.length > 0 &&
      segments.every((s) => s.verification_status === "HUMAN_APPROVED");
  if (preview)
    return (
      <>
        <Button variant="outline" onClick={() => setPreview(null)}>
          Back to review
        </Button>
        <Reader sermon={preview} preview onError={notify} />
      </>
    );
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            {dateLabel(item.khutba_date)} ·{" "}
            {item.status.replaceAll("_", " ").toLowerCase()}
          </div>
          <h1>{item.title}</h1>
        </div>
        <Button
          variant="outline"
          onClick={() =>
            run(async () =>
              setPreview(await api<Sermon>(`admin/sermons/${id}/preview`)),
            )
          }
            disabled={busy || !done || unsaved}
        >
          Reader preview
        </Button>
      </div>
      {item.failure_reason && <p className="notice">{item.failure_reason}</p>}
      {item.status==="PUBLISHED"&&<LiveAdmin id={item.id} notify={notify}/>}
      <TitleEditor item={item} notify={notify} onSaved={title => setItem(previous => previous ? {...previous, title} : previous)}/>
      {["SOURCE_REVIEW_REQUIRED", "DRAFT", "FAILED"].includes(item.status) && (
        <section className="panel">
          <h2>Check the extracted Arabic</h2>
          <p className="muted">
            Make sure the text is complete before starting. Translation uses the
            same sources and checks as the mobile app.
          </p>
          <Textarea
            aria-label="Extracted Arabic"
            className="source-arabic"
            lang="ar"
            dir="rtl"
            rows={16}
            value={source}
            readOnly={item.status!=="SOURCE_REVIEW_REQUIRED"}
            onChange={(e) => setSource(e.target.value)}
          />
          <Button
            disabled={busy || !source.trim()}
            onClick={() =>
              run(async () => {
                if(item.status==="SOURCE_REVIEW_REQUIRED"){
                  const draft=await api<Sermon>(`admin/sermons/${id}/source-text`, "PUT", {arabic_text:source});
                  setItem(draft);
                }
                await api(`admin/sermons/${id}/translate`, "POST");
                await refresh();
              })
            }
          >
            {busy ? "Starting…" : "Create grounded translation"}
          </Button>
        </section>
      )}
      {item.status === "TRANSLATING" && (
        <section className="panel" role="status">
          <h2>Translating your khutba</h2>
          <p>
            {item.target_language === "da" ? "Preparing Danish from the approved English text." : "Finding sources and preparing the English text."} You can leave this
            page and return later.
          </p>
          <Progress
            value={segments.length ? (done / segments.length) * 100 : 0}
            aria-label="Translation progress"
          />
          <p>
            {done} of {segments.length} passages prepared. Source checks may
            take several minutes.
          </p>
          {pollError && <Button onClick={refresh}>Reconnect</Button>}
        </section>
      )}
      {["REVIEW_REQUIRED", "PUBLISHED", "HIDDEN"].includes(item.status) && (
        <>
          <p className="notice">
            Check the translation and its sources before approving. Edits can
            change citation placement; use Reader preview to verify it.
          </p>
          {segments.map((segment) => (
            <ReviewSegment
              key={segment.id}
              {...{ segment, id, notify }}
              language={item.target_language}
              readOnly={item.status!=="REVIEW_REQUIRED"}
              onDirty={onDirty}
              onSaved={refresh}
            />
          ))}
          {item.status === "REVIEW_REQUIRED" && (
            <section className="panel">
              <h2>Ready for readers?</h2>
              <p>
                {approved
                  ? "All passages are approved."
                  : "Approve every passage before publishing."}
              </p>
              <Button
                disabled={!approved || busy || unsaved}
                onClick={() => setConfirm(true)}
              >
                Publish khutba
              </Button>
              {unsaved&&<p>Save your changes before previewing or publishing.</p>}
            </section>
          )}
          {item.status === "PUBLISHED" && item.target_language !== "da" && (
            <Button variant="outline" onClick={() => go("definitions/" + id)}>
              Add missing word meanings
            </Button>
          )}
        </>
      )}
      <AlertDialog open={confirm} onOpenChange={setConfirm}>
        <AlertDialogContent>
          <AlertDialogTitle>Publish this khutba?</AlertDialogTitle>
          <AlertDialogDescription>
            Readers will be able to open this approved translation.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Review again</AlertDialogCancel>
            <AlertDialogAction
              disabled={busy}
              onClick={(e) => {
                e.preventDefault();
                void run(async () => {
                  await api(`admin/sermons/${id}/publish`, "POST");
                  setConfirm(false);
                  notify("Khutba published.");
                  go(item.target_language === "da" ? "admin" : "definitions/" + id);
                });
              }}
            >
              Publish
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
export function Definitions({ id, go, notify }: Props & { id: string }) {
  const [failed,setFailed]=useState(false);
  const [items, setItems] = useState<Candidate[] | null>(null),
    [busy, setBusy] = useState<string | null>(null);
  const refresh=useCallback(()=> {
    setFailed(false);
    api<Candidate[]>(`admin/sermons/${id}/glossary-candidates`)
      .then(setItems)
      .catch((e) => {setFailed(true);notify(e.message);});
  }, [id,notify]);
  useEffect(()=>{refresh();},[refresh]);
  async function submit(e: React.FormEvent<HTMLFormElement>, c: Candidate) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(c.arabic_term);
    try {
      await api(`admin/sermons/${id}/glossary-contributions`, "POST", {
        ...c,
        literal_translation: f.get("phrase"),
        meaning: f.get("meaning"),
      });
      setItems((items) => items!.filter((i) => i !== c));
      notify("Definition submitted for owner approval.");
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(null);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">Optional · after publishing</div>
          <h1>Add word meanings</h1>
          <p>
            Your khutba is published. These definitions will join the shared
            glossary after the app owner approves them.
          </p>
        </div>
        <Button variant="outline" onClick={() => go("admin")}>
          Done / skip
        </Button>
      </div>
      {failed?<div className="empty"><p>Your khutba remains published. The word list could not be loaded.</p><Button onClick={refresh}>Try again</Button></div>:items === null ? (
        <p>Loading words…</p>
      ) : items.length === 0 ? (
        <div className="empty">No missing definitions were found.</div>
      ) : (
        items.map((c) => (
          <form
            className="panel"
            key={c.segment_id + c.arabic_term}
            onSubmit={(e) => submit(e, c)}
          >
            <h2 lang="ar" dir="rtl">
              {c.arabic_term}
            </h2>
            <blockquote>{c.sentence}</blockquote>
            <label className="field">
              English phrase directly before this Arabic word
              <Input name="phrase" required />
            </label>
            <label className="field">
              Definition
              <Textarea
                name="meaning"
                minLength={3}
                required
                placeholder="Explain the meaning in this context"
              />
            </label>
            <Button disabled={!!busy}>
              {busy === c.arabic_term ? "Saving…" : "Add definition"}
            </Button>
          </form>
        ))
      )}
    </>
  );
}
const emptyTerm: Glossary = {
  arabic_term: "",
  literal_translation: "",
  meaning: "",
  arabic_variations: "",
  alternative_context_meanings: "",
};
export function Settings({ notify }: Props) {
  const [mosque, setMosque] = useState<Mosque | null>(null),
    [name, setName] = useState(""),
    [terms, setTerms] = useState<Glossary[]>([]),
    [city, setCity] = useState(""),
    [term, setTerm] = useState<Glossary>(emptyTerm),
    [busy, setBusy] = useState(false),
    [remove, setRemove] = useState<Glossary | null>(null);
  async function refresh() {
    const [m, g] = await Promise.all([
      api<Mosque>("admin/profile"),
      api<Glossary[]>("admin/glossary"),
    ]);
    setMosque(m);
    setName(m.name);
    setCity(m.city);
    setTerms(g);
  }
  useEffect(() => {
    refresh().catch((e) => notify(e.message));
  }, [notify]);
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <h1>Settings & glossary</h1>
      </div>
      <div className="settings-grid">
        <section className="panel">
          <h2>Mosque profile</h2>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void run(async () => {
                setMosque(
                  await api<Mosque>("admin/profile", "PATCH", {
                    mosque_name: name,
                    city,
                  }),
                );
                notify("Mosque profile updated.");
              });
            }}
          >
            <Field
              name="mosque_name"
              label="Mosque name"
              value={name}
              onChange={setName}
              minLength={2}
            />
            <p className="muted">
              {mosque?.country}
            </p>
            <Field name="city" label="City" value={city} onChange={setCity} minLength={2}/>
            <Button disabled={busy || !mosque}>Save profile</Button>
          </form>
        </section>
        <section className="panel">
          <h2>Change password</h2>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const form = e.currentTarget,
                f = new FormData(form);
              void run(async () => {
                await api("admin/password", "PUT", {
                  current_password: f.get("current"),
                  new_password: f.get("new"),
                });
                form.reset();
                notify("Password changed.");
              });
            }}
          >
            <label className="field">
              Current password
              <Input
                name="current"
                type="password"
                autoComplete="current-password"
                required
              />
            </label>
            <label className="field">
              New password (at least 6 characters)
              <Input
                name="new"
                type="password"
                autoComplete="new-password"
                minLength={6}
                required
              />
            </label>
            <Button disabled={busy}>Change password</Button>
          </form>
        </section>
      </div>
      <section className="panel">
        <h2>{term.id ? "Edit glossary term" : "Add a mosque glossary term"}</h2>
        <p className="muted">
          New or edited entries need owner approval before they are used. Use definitions
          specific enough to avoid confusing different meanings.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              await api(
                "admin/glossary" + (term.id ? "/" + term.id : ""),
                term.id ? "PUT" : "POST",
                term,
              );
              setTerm(emptyTerm);
              await refresh();
              notify("Glossary submitted for owner approval.");
            });
          }}
          className="form-grid"
        >
          {(
            [
              ["arabic_term", "Arabic word / expression"],
              ["literal_translation", "English meaning"],
              ["meaning", "Explanation"],
              ["arabic_variations", "Arabic variations (optional)"],
              ["alternative_context_meanings", "Other contexts (optional)"],
            ] as const
          ).map(([key, label]) => (
            <label className="field" key={key}>
              {label}
              <Textarea
                dir={key.startsWith("arabic") ? "rtl" : "auto"}
                value={term[key]}
                required={[
                  "arabic_term",
                  "literal_translation",
                  "meaning",
                ].includes(key)}
                onChange={(e) => setTerm({ ...term, [key]: e.target.value })}
              />
            </label>
          ))}
          <div className="actions">
            <Button disabled={busy}>Save term</Button>
            {term.id && (
              <Button
                variant="outline"
                type="button"
                onClick={() => setTerm(emptyTerm)}
              >
                Cancel edit
              </Button>
            )}
          </div>
        </form>
      </section>
      <div className="stack">
        {terms.map((t) => (
          <section className="panel khutba-row" key={t.id}>
            <div>
              <h3>
                <span lang="ar">{t.arabic_term}</span> · {t.literal_translation}
              </h3>
              <p>{t.meaning}</p>
              <p className="muted">{t.approval_status === "PENDING" ? "Awaiting approval" : t.approval_status === "REJECTED" ? "Rejected — edit to resubmit" : "Approved"}</p>
            </div>
            <div className="actions">
              <Button
                variant="outline"
                onClick={() => {
                  setTerm(t);
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
              >
                Edit
              </Button>
              <Button
                variant="ghost"
                className="danger"
                onClick={() => setRemove(t)}
              >
                Remove
              </Button>
            </div>
          </section>
        ))}
      </div>
      <AlertDialog open={!!remove} onOpenChange={(v) => !v && setRemove(null)}>
        <AlertDialogContent>
          <AlertDialogTitle>Remove glossary entry?</AlertDialogTitle>
          <AlertDialogDescription>
            This removes {remove?.arabic_term} from your mosque’s glossary.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={busy}
              onClick={(e) => {
                e.preventDefault();
                void run(async () => {
                  await api("admin/glossary/" + remove?.id, "DELETE");
                  setRemove(null);
                  await refresh();
                });
              }}
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
