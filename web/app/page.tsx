"use client";
import { useCallback, useEffect, useState } from "react";
import {
  BookOpen,
  Landmark,
  ArrowLeft,
  Search,
  ChevronRight,
  Download,
  Bookmark,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Reader } from "@/components/khutba-reader";
import {AdminGate} from "@/components/admin-gate";
import {WebTools} from "@/components/web-tools";
import {OwnerDashboard, PasswordRecovery} from "@/components/owner-dashboard";
import {
  Auth,
  Admin,
  Review,
  Definitions,
  Settings,
} from "@/components/khutba-admin";
import {
  api,
  ApiError,
  Mosque,
  Sermon,
  dateLabel,
  groupLabel,
  storage,
  saveLocal,
} from "@/lib/khutba";
function MosqueList({
  go,
  notify,
}: {
  go: (p: string) => void;
  notify: (m: string) => void;
}) {
  const [items, setItems] = useState<Mosque[]>([]),
    [query, setQuery] = useState(""),
    [loading, setLoading] = useState(true),
    [failed, setFailed] = useState(false),
    [preferred, setPreferred] = useState("");
  const refresh=useCallback(async()=> {
    setLoading(true);
    setFailed(false);
    try {
      setItems(await api<Mosque[]>("reader/mosques"));
    } catch (e) {
      setFailed(true);
      notify((e as Error).message);
    } finally {
      setLoading(false);
    }
  },[notify]);
  useEffect(() => {
    setPreferred(storage("preferred-mosque", ""));
    void refresh();
  }, [refresh]);
  const filtered = items
    .filter((m) =>
      `${m.name} ${m.city} ${m.country}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    )
    .sort(
      (a, b) =>
        Number(b.id === preferred) - Number(a.id === preferred) ||
        a.name.localeCompare(b.name),
    );
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">English · Dansk</div>
          <h1>Choose your mosque</h1>
        </div>
        <Button variant="outline" onClick={() => go("saved")}>
          <Bookmark size={18} />
          Saved khutbas
        </Button>
      </div>
      <div className="search-row mosque-search">
        <Search size={20} />
        <Input
          aria-label="Search mosques"
          placeholder="Mosque name or city"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      {loading ? (
        <p role="status">Loading mosques…</p>
      ) : failed ? (
        <div className="empty">
          <p>We couldn’t load the mosques.</p>
          <Button onClick={refresh}>Try again</Button>
        </div>
      ) : (
        <div className="mosque-grid">
          {filtered.map((m) => (
            <button
              className="mosque-card"
              key={m.id}
              onClick={() => {
                try {
                  saveLocal("preferred-mosque", m.id);
                } catch {}
                go("mosque/" + m.id);
              }}
            >
              <Landmark size={28} />
              <span>
                <strong>{m.name}</strong>
                <small>
                  {m.city}, {m.country}
                  {m.id === preferred ? " · Last visited" : ""}
                </small>
              </span>
              <ChevronRight size={20} />
            </button>
          ))}
          {!filtered.length && (
            <p className="empty">No mosques match your search.</p>
          )}
        </div>
      )}
    </>
  );
}
function SermonList({
  id,
  go,
  notify,
  saved = false,
}: {
  id?: string;
  go: (p: string) => void;
  notify: (m: string) => void;
  saved?: boolean;
}) {
  const [items, setItems] = useState<Sermon[]>([]),
    [name, setName] = useState(saved ? "Saved khutbas" : "Khutbas"),
    [language, setLanguage] = useState("all"),
    [loading, setLoading] = useState(true),
    [failed, setFailed] = useState(false);
  const refresh=useCallback(async()=> {
    setLoading(true);
    setFailed(false);
    try {
      if (saved) {
        setItems(Object.values(storage<Record<string, Sermon>>("saved", {})));
      } else {
        const [list, mosques] = await Promise.all([
          api<Sermon[]>(`reader/mosques/${id}/sermons`),
          api<Mosque[]>("reader/mosques"),
        ]);
        setItems(list);
        setName(mosques.find((m) => m.id === id)?.name || "Khutbas");
        const copies = storage<Record<string, Sermon>>("saved", {});
        for (const key of Object.keys(copies))
          if (copies[key].mosque_id === id && !list.some((s) => s.id === key))
            delete copies[key];
        try {
          saveLocal("saved", copies);
        } catch {}
      }
    } catch (e) {
      setFailed(true);
      notify((e as Error).message);
    } finally {
      setLoading(false);
    }
  },[id,saved,notify]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  const visible = items.filter(s => language === "all" || (s.target_language || "en") === language);
  const groups = [...visible].sort((a,b)=>b.khutba_date.localeCompare(a.khutba_date)).reduce<Record<string,Sermon[]>>((all,s)=>{const label=groupLabel(s.khutba_date);(all[label]??=[]).push(s);return all;},{});
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            {saved ? "On this device" : "From your mosque"}
          </div>
          <h1>{name}</h1>
        </div>
        {!saved && (
          <Button variant="outline" onClick={refresh}>
            Refresh
          </Button>
        )}
      </div>
      {saved && (
        <p className="muted">
          Saved copies are available on this browser. They may be older than the
          published version.
        </p>
      )}
      <div className="actions" aria-label="Translation language">
        {[["all", "All languages"], ["en", "English"], ["da", "Dansk"]].map(([value, label]) =>
          <Button key={value} variant={language === value ? "default" : "outline"} aria-pressed={language === value} onClick={() => setLanguage(value)}>{label}</Button>)}
      </div>
      {!loading && items.length > 0 && visible.length === 0 && <p>No published translation in this language yet. Choose English to read the available khutbas.</p>}
      {loading ? (
        <p role="status">Loading khutbas…</p>
      ) : failed ? (
        <Button onClick={refresh}>Try again</Button>
      ) : !items.length ? (
        <div className="empty">
          {saved
            ? "Open a khutba and choose Save for offline to keep a copy here."
            : "No published khutbas yet. Check back on Friday."}
        </div>
      ) : (
        Object.entries(groups).map(([group, list]) => (
          <section className="date-group" key={group}>
            <h2>{group}</h2>
            <div className="stack">
              {list?.map((s) => (
                <button
                  className="sermon-card"
                  key={s.id}
                  onClick={() => go((saved ? "saved-read/" : "read/") + s.id)}
                >
                  <span className="date-tile">
                    {new Date(s.khutba_date + "T12:00:00").getDate()}
                    <small>
                      {new Intl.DateTimeFormat("en", { month: "short" }).format(
                        new Date(s.khutba_date + "T12:00:00"),
                      )}
                    </small>
                  </span>
                  <span>
                    <strong>{s.title}</strong>
                    <small>{dateLabel(s.khutba_date)} · {s.target_language === "da" ? "Dansk" : "English"}</small>
                  </span>
                  <ChevronRight />
                </button>
              ))}
            </div>
          </section>
        ))
      )}
    </>
  );
}
function ReadPage({
  id,
  notify,
  saved = false,
}: {
  id: string;
  notify: (m: string) => void;
  saved?: boolean;
}) {
  const [item, setItem] = useState<Sermon | null>(null),
    [failed, setFailed] = useState(false),
    [offline, setOffline] = useState(saved);
  const refresh=useCallback(async()=> {
    setFailed(false);
    try {
      if (saved) {
        const copy = storage<Record<string, Sermon>>("saved", {})[id];
        if (!copy) throw Error("This saved copy is no longer on your device.");
        setItem(copy);
        return;
      }
      setItem(await api<Sermon>("reader/sermons/" + id));
      setOffline(false);
    } catch (e) {
      const copy = storage<Record<string, Sermon>>("saved", {})[id];
      if (!saved && copy && (!(e instanceof ApiError) || e.status === 503)) {
        setItem(copy);
        setOffline(true);
      } else {
        setFailed(true);
        if (e instanceof ApiError && e.status === 404) {
          const all = storage<Record<string, Sermon>>("saved", {});
          delete all[id];
          try {
            saveLocal("saved", all);
          } catch {}
        }
        notify((e as Error).message);
      }
    }
  },[id,saved,notify]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  return item ? (
    <Reader {...{ sermon: item, offline }} onError={notify} />
  ) : (
    <div className="empty">
      <p>{failed ? "This khutba could not be opened." : "Loading khutba…"}</p>
      {failed && <Button onClick={refresh}>Try again</Button>}
    </div>
  );
}
export default function Home() {
  const [ready,setReady]=useState(false);
  const [path, setPath] = useState(""),
    [message, setMessage] = useState(""),
    [install, setInstall] = useState(false);
  function go(value: string) {
    location.hash = value;
    setPath(value);
    setMessage("");
  }
  useEffect(() => {
    setReady(true);
    const change = () => {
      setPath(location.hash.slice(1));
      window.scrollTo(0, 0);
    };
    change();
    window.addEventListener("hashchange", change);
    if ("serviceWorker" in navigator && window.isSecureContext)
      navigator.serviceWorker.register("/sw.js").then(()=>navigator.serviceWorker.ready).then(reg=>{
        const urls=performance.getEntriesByType("resource").map(entry=>entry.name).filter(name=>{const url=new URL(name);return url.origin===location.origin&&/^\/(assets\/|_next\/static\/)/.test(url.pathname);});
        reg.active?.postMessage({type:"CACHE_SHELL_ASSETS",urls});
      }).catch(() => {});
    return () => window.removeEventListener("hashchange", change);
  }, []);
  const [view, id] = path.split("/");
  const admin = ["admin", "review", "definitions", "settings", "owner"].includes(view);
  const props = { go, notify: setMessage };
  return (
    <main className="shell" data-ready={ready}>
      <WebTools/>
      <a className="skip-link" href="#main-content" onClick={e=>{e.preventDefault();document.getElementById("main-content")?.focus();}}>
        Skip to content
      </a>
      <header className="masthead">
        <button
          className="brand"
          onClick={() => go("")}
          aria-label="Khutba home"
        >
          <BookOpen aria-hidden /> Khutba
        </button>
        <div className="actions">
          {admin ? (
            <Button
              variant="ghost"
              onClick={async () => {
                try {
                  await api("auth/logout", "POST");
                  go("");
                } catch (e) {
                  setMessage((e as Error).message);
                }
              }}
            >
              Sign out
            </Button>
          ) : (
            <button className="install-link" onClick={() => setInstall(true)}>
              <Download size={16} />
              <span>Add to Home Screen</span>
            </button>
          )}
        </div>
      </header>
      {path && (
        <nav className="back-nav">
          <Button
            variant="ghost"
            onClick={() =>
              go(
                admin
                  ? view === "admin" || view === "owner"
                    ? ""
                    : "admin"
                  : ["read", "mosque", "saved-read"].includes(view)
                    ? "mosques"
                    : "",
              )
            }
          >
            <ArrowLeft size={17} />
            {admin && view !== "admin" && view !== "owner" ? "Your khutbas" : "Back"}
          </Button>
        </nav>
      )}
      {message && (
        <div className="notice message" role="alert">
          <span>{message}</span>
          <button aria-label="Dismiss message" onClick={() => setMessage("")}>
            <X size={20} />
          </button>
        </div>
      )}
      <div id="main-content" tabIndex={-1} key={path}>
        {!path ? (
          <section className="welcome">
            <div className="eyebrow">Your Friday khutba</div>
            <h1>
              Your mosque’s khutba,
              <br />
              <em>in English or Danish.</em>
            </h1>
            <p className="welcome-copy">
              Read the translation, with source references and word meanings.
            </p>
            <div className="role-grid">
              <button
                className="role-card primary"
                disabled={!ready}
                onClick={() => go("mosques")}
              >
                <BookOpen />
                <strong>Read a khutba</strong>
                <span>Choose your mosque. No account needed.</span>
                <ChevronRight className="role-arrow" />
              </button>
              <button className="role-card" disabled={!ready} onClick={() => go("login")}>
                <Landmark />
                <strong>Mosque sign in</strong>
                <span>Prepare and share your Friday khutba.</span>
                <ChevronRight className="role-arrow" />
              </button>
            </div>
            <button className="saved-shortcut" onClick={() => go("saved")}>
              <Bookmark size={18} />
              Open saved khutbas
            </button>
            <p className="opening-hours">
              Usually available Fridays, 10:00–15:00 Copenhagen time.
              <br />
              Saved khutbas can be read outside these hours.
            </p>
          </section>
        ) : view === "mosques" ? (
          <MosqueList {...props} />
        ) : view === "mosque" && id ? (
          <SermonList {...props} id={id} />
        ) : view === "saved" ? (
          <SermonList {...props} saved />
        ) : (view === "read" || view === "saved-read") && id ? (
          <ReadPage id={id} saved={view === "saved-read"} notify={setMessage} />
        ) : view === "login" ? (
          <Auth {...props} />
        ) : view === "owner" ? (
          <OwnerDashboard {...props}/>
        ) : view === "reset" && id ? (
          <PasswordRecovery {...props} token={id}/>
        ) : view === "recovery" ? (
          <PasswordRecovery {...props}/>
        ) : view === "admin" ? (
          <AdminGate><Admin {...props} /></AdminGate>
        ) : view === "review" && id ? (
          <AdminGate><Review {...props} id={id} /></AdminGate>
        ) : view === "definitions" && id ? (
          <AdminGate><Definitions {...props} id={id} /></AdminGate>
        ) : view === "settings" ? (
          <AdminGate><Settings {...props} /></AdminGate>
        ) : (
          <div className="empty">
            <h1>Page not found</h1>
            <Button onClick={() => go("")}>Go home</Button>
          </div>
        )}
      </div>
      <footer>
        Khutba · Prepared by your mosque, with sources you can check.
      </footer>
      <Dialog open={install} onOpenChange={setInstall}>
        <DialogContent>
          <DialogTitle>Keep Khutba close</DialogTitle>
          <DialogDescription>
            Add it to your iPhone or iPad Home Screen.
          </DialogDescription>
          <ol>
            <li>Open this site in Safari.</li>
            <li>Tap Share, then Add to Home Screen.</li>
            <li>Tap Add. Khutba will open like an app.</li>
          </ol>
          <p>
            Save the khutbas you want to read offline. Browser storage can be
            cleared by your device, so keep a PDF for a lasting copy.
          </p>
        </DialogContent>
      </Dialog>
    </main>
  );
}
