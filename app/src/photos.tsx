import { useEffect, useState } from 'preact/hooks';
import { api, fetchPrivateImage, type SiteContent } from './api';
import { BUSINESS, GUIDES, TEAM } from './content';

const block = (event: Event) => event.preventDefault();

/**
 * An image that discourages copying: no drag, no right-click menu, no selection,
 * and a transparent layer above it. Screenshots cannot be blocked by any website.
 */
export function ProtectedImage({ src, alt, class: className = '' }: { src: string; alt: string; class?: string }) {
  return (
    <span class={`protected ${className}`} onContextMenu={block} onDragStart={block}>
      <img src={src} alt={alt} draggable={false} loading="lazy" decoding="async" />
      <span class="protected-shield" aria-hidden="true" />
    </span>
  );
}

const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]!.toUpperCase()).join('') || '?';

/** Avatar for a private profile photo. Falls back to initials when there is no photo or no access. */
export function Avatar({ url, name, locked, size = 40 }: { url: string | null; name: string; locked?: boolean; size?: number }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    setSrc(null);
    if (url) {
      void fetchPrivateImage(url).then((value) => {
        objectUrl = value;
        if (active) setSrc(value);
        else if (value) URL.revokeObjectURL(value);
      });
    }
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [url]);
  return (
    <span class={`avatar ${locked ? 'is-locked' : ''}`} style={{ width: `${size}px`, height: `${size}px` }}
      title={locked ? 'Profile photo locked' : undefined}>
      {src ? <ProtectedImage src={src} alt={`${name}'s profile photo`} /> : <span class="avatar-initials">{initials(name)}</span>}
      {locked && <span class="avatar-lock" aria-label="Locked">🔒</span>}
    </span>
  );
}

export const DEFAULT_SITE: SiteContent = {
  team: TEAM.map((person) => ({ ...person, photo_id: null, photo_url: null })),
  guides: GUIDES.map((person) => ({ ...person, photo_id: null, photo_url: null })),
  business: { name: BUSINESS.name, email: BUSINESS.email, phone: BUSINESS.phone, address: BUSINESS.address, last_updated: BUSINESS.lastUpdated },
};

let cache: Promise<SiteContent> | null = null;

/** Public site content edited by the superadmin, with built-in defaults if it cannot load. */
export function useSiteContent(): SiteContent {
  const [content, setContent] = useState<SiteContent>(DEFAULT_SITE);
  useEffect(() => {
    let active = true;
    cache ??= api.siteContent().catch(() => { cache = null; return DEFAULT_SITE; });
    void cache.then((value) => { if (active) setContent(value); });
    return () => { active = false; };
  }, []);
  return content;
}

export function refreshSiteContent() { cache = null; }
