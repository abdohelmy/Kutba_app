export type SentenceAlignment = {
  translation_start: number; translation_end: number;
  arabic_start: number; arabic_end: number;
};

// Keep an edited sentence attached to its Arabic source. Edits spanning several
// mapped sentences discard those mappings until the reviewer refreshes them.
export function moveAlignment(links: SentenceAlignment[], before: string, after: string) {
  if (before === after) return links;
  let start = 0, suffix = 0;
  while (start < Math.min(before.length, after.length) && before[start] === after[start]) start++;
  while (suffix < Math.min(before.length, after.length) - start &&
    before[before.length - 1 - suffix] === after[after.length - 1 - suffix]) suffix++;
  const end = before.length - suffix, delta = after.length - before.length;
  return links.flatMap(link => {
    const a = link.translation_start, b = link.translation_end;
    if (b <= start && !(start === end && b === start && b === before.length)) return [link];
    if (a >= end && !(start === end && a === start))
      return [{...link, translation_start:a + delta, translation_end:b + delta}];
    if (a <= start && b >= end && b + delta > a)
      return [{...link, translation_end:b + delta}];
    return [];
  });
}

export function selectedArabic(links: SentenceAlignment[], start: number, end: number, length: number) {
  return links.filter(link => start === end
    ? start >= link.translation_start && (start < link.translation_end || start === length && start === link.translation_end)
    : link.translation_start < end && link.translation_end > start
  ).map(link => ({start:link.arabic_start, end:link.arabic_end}));
}
