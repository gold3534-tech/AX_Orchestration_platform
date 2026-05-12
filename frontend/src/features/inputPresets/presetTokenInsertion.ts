export type TextSelection = {
  start: number;
  end: number;
};

export function presetToken(key: string) {
  return `{${key}}`;
}

export function appendPresetTokenOnce(value: string, key: string) {
  const token = presetToken(key);
  if (value.includes(token)) return value;
  if (!value.trim()) return token;
  return value.endsWith(' ') || value.endsWith('\n') ? `${value}${token}` : `${value} ${token}`;
}

export function insertPresetTokenOnce(value: string, key: string, selection: TextSelection | null) {
  const token = presetToken(key);
  if (value.includes(token)) return value;
  if (!selection) return appendPresetTokenOnce(value, key);
  return `${value.slice(0, selection.start)}${token}${value.slice(selection.end)}`;
}

export function removePresetToken(value: string, key: string) {
  const token = presetToken(key);
  return value
    .split(token)
    .join('')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n[ \t]+/g, '\n')
    .trim();
}
