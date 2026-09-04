import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Utility for combining Tailwind classes cleanly with conflict resolution.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format large numbers with commas.
 */
export function formatNumber(num: number | string | null | undefined) {
  const value = typeof num === 'string' ? parseFloat(num) : num;
  return new Intl.NumberFormat().format(value || 0);
}

export function cleanRarityLabel(rarity: string) {
  return rarity
    .replace(
      /[\u2700-\u27bf]|[\u2190-\u21ff]|[\u2000-\u206f]|[\u2600-\u26ff]|[\u2b00-\u2bff]|[\u00a0-\u00bf]|\u2013|\u2014/g,
      '',
    )
    .trim();
}

export * from './haptics';

/**
 * Guaranteed-render placeholder for broken/expired external images.
 * Inline SVG data URI (no network) so it never 404s or hotlink-blocks.
 */
const PLACEHOLDER_SVG =
  "<svg xmlns='http://www.w3.org/2000/svg' width='300' height='420' viewBox='0 0 300 420'>" +
  "<rect width='300' height='420' fill='#090b14'/>" +
  "<rect x='8' y='8' width='284' height='404' rx='10' fill='none' stroke='#1f2230' stroke-width='2'/>" +
  "<text x='150' y='200' font-family='Arial,Helvetica,sans-serif' font-size='26' font-weight='800' fill='#2a2d3a' text-anchor='middle' letter-spacing='3'>ANINEXUS</text>" +
  "<text x='150' y='226' font-family='Arial,Helvetica,sans-serif' font-size='11' font-weight='600' fill='#3a3d4a' text-anchor='middle' letter-spacing='2'>NO IMAGE</text>" +
  '</svg>';

export const FALLBACK_IMAGE = `data:image/svg+xml;utf8,${encodeURIComponent(PLACEHOLDER_SVG)}`;
