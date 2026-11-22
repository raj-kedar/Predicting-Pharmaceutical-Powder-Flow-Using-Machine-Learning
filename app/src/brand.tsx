import logoMark from './assets/logo-mark-128.webp';
import logoWordmark from './assets/logo-wordmark.webp';

/** The round FlowLytix emblem used in headers, sidebars and sign-in pages. */
export function BrandMark({ size = 38 }: { size?: number }) {
  return (
    <span class="brand-mark" aria-hidden="true" style={{ width: `${size}px`, height: `${size}px` }}>
      <img src={logoMark} alt="" width={size} height={size} draggable={false} />
    </span>
  );
}

/** Full logo with the "Powder flow detection" tagline. */
export function BrandWordmark({ class: className = '' }: { class?: string }) {
  return <img class={`brand-wordmark ${className}`} src={logoWordmark} alt="FlowLytix, powder flow detection"
    width={960} height={540} loading="lazy" draggable={false} />;
}
