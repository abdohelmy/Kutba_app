export type Mosque = {
  id: string;
  name: string;
  city: string;
  country: string;
};
export type Citation = {
  chunk_id: string;
  source_id: string;
  title: string;
  display_reference?: string;
  authority: string;
  excerpt: string;
  arabic_excerpt?: string;
  transliteration?: string;
  url?: string;
  anchor_valid?: boolean;
  translation_start?: number;
  translation_end?: number;
};
export type Term = {
  arabic_term: string;
  meaning: string;
  literal_translation: string;
  display_term: string;
  english_phrase?: string;
  localized_phrase?: string;
  popup_phrase?: string;
  popup_language?: string;
  transliteration?: string;
  alternative_context_meanings?: string;
  translation_start?: number;
  translation_end?: number;
};
export type Segment = {
  id: string;
  ordinal: number;
  arabic_text?: string;
  english_text?: string;
  localized_glossary?: Term[];
  translated_text?: string;
  verification_status?: string;
  reviewer_note?: string;
  issues?: string[];
  citations: Citation[];
  glossary_terms?: Term[];
};
export type Sermon = {
  id: string;
  title: string;
  khutba_date: string;
  mosque_id: string;
  status: string;
  target_language?: string;
  english_sermon_id?: string;
  failure_reason?: string;
  segments?: Segment[];
};
export type Candidate = {
  segment_id: string;
  arabic_term: string;
  sentence: string;
};
export type Glossary = {
  id?: string;
  arabic_term: string;
  literal_translation: string;
  meaning: string;
  arabic_variations: string;
  alternative_context_meanings: string;
  approval_status?: string;
};
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api/" + path, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers:
      body instanceof FormData
        ? {}
        : body
          ? { "Content-Type": "application/json" }
          : {},
    body:
      body instanceof FormData
        ? body
        : body === undefined
          ? undefined
          : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = (await response
      .json()
      .catch(() => ({ detail: "Request failed. Try again." }))) as {
      detail: unknown;
    };
    let detail = data.detail;
    if (Array.isArray(detail))
      detail = detail
        .map(
          (d: { loc?: string[]; msg: string }) =>
            `${d.loc?.slice(1).join(" ") || "Request"}: ${d.msg}`,
        )
        .join(". ");
    throw new ApiError(
      typeof detail === "string" ? detail : "Request failed",
      response.status,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export function friday() {
  const p = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Copenhagen",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const v = (k: string) => p.find((x) => x.type === k)!.value;
  const d = new Date(`${v("year")}-${v("month")}-${v("day")}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + ((5 - d.getUTCDay() + 7) % 7));
  return d.toISOString().slice(0, 10);
}
export function dateLabel(s: string) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(s + "T12:00:00"));
}
export function groupLabel(date: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Copenhagen",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = (key: string) => parts.find((p) => p.type === key)!.value;
  const monday = new Date(
    `${value("year")}-${value("month")}-${value("day")}T12:00:00Z`,
  );
  monday.setUTCDate(monday.getUTCDate() - ((monday.getUTCDay() + 6) % 7));
  const sunday = new Date(monday);
  sunday.setUTCDate(sunday.getUTCDate() + 6);
  if (
    date >= monday.toISOString().slice(0, 10) &&
    date <= sunday.toISOString().slice(0, 10)
  )
    return "This week";
  if (date > sunday.toISOString().slice(0, 10)) return "Upcoming";
  return new Intl.DateTimeFormat("en-GB", {
    month: "long",
    year: "numeric",
  }).format(new Date(date + "T12:00:00"));
}
export function safeURL(url?: string) {
  try {
    const u = new URL(url || "");
    return u.protocol === "https:" ? u.href : undefined;
  } catch {
    return undefined;
  }
}
export function storage<T>(key: string, fallback: T): T {
  try {
    return (
      JSON.parse(localStorage.getItem("khutba:" + key) || "null") ?? fallback
    );
  } catch {
    return fallback;
  }
}
export function saveLocal(key: string, value: unknown) {
  try {
    localStorage.setItem("khutba:" + key, JSON.stringify(value));
  } catch {
    throw Error(
      "This browser could not save the item. Check available storage or private browsing settings.",
    );
  }
}
