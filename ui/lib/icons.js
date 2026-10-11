// ============================================================================
//  icons.js —— 内联 SVG 图标（描边风格，20px 网格）
//  不用 Segoe Fluent Icons 字体：字体缺字时会掉成方块，内联 SVG 到处都稳。
// ============================================================================

window.ICONS = {
  gear:
    '<circle cx="12" cy="12" r="3.1"/><path d="M12 2.9v2.5M12 18.6v2.5M4.2 7.6l2.2 1.3M17.6 15.1l2.2 1.3M4.2 16.4l2.2-1.3M17.6 8.9l2.2-1.3"/>',
  palette:
    '<path d="M12 3.2a8.8 8.8 0 1 0 0 17.6h1.5a1.9 1.9 0 0 0 0-3.8 1.9 1.9 0 0 1 0-3.8h1.6A4.7 4.7 0 0 0 19.8 8.5C19.8 5.6 16.4 3.2 12 3.2Z"/><circle cx="8.4" cy="9.3" r="1.05" fill="currentColor" stroke="none"/><circle cx="12" cy="7.4" r="1.05" fill="currentColor" stroke="none"/>',
  island:
    '<rect x="5" y="4.8" width="14" height="7.4" rx="3.7"/><path d="M8.4 16.4h7.2"/><path d="M10.4 19.4h3.2"/>',
  calendar:
    '<rect x="3.6" y="5.2" width="16.8" height="15" rx="2.6"/><path d="M3.6 10.2h16.8M8.2 3.4v3.4M15.8 3.4v3.4"/>',
  book:
    '<path d="M4.6 6.2A2.2 2.2 0 0 1 6.8 4h12V17H6.8a2.2 2.2 0 0 0-2.2 2.2Z"/><path d="M4.6 19.2A2.2 2.2 0 0 1 6.8 17H18.8v3H6.8a2.2 2.2 0 0 1-2.2-.8Z"/>',
  puzzle:
    '<path d="M9.2 4.4a1.9 1.9 0 0 1 3.8 0v1.2h3.4a1.5 1.5 0 0 1 1.5 1.5v3.2h1.2a1.9 1.9 0 0 1 0 3.8h-1.2V17a1.5 1.5 0 0 1-1.5 1.5h-3.2v-1.2a1.9 1.9 0 0 0-3.8 0v1.2H6.6A1.5 1.5 0 0 1 5.1 17v-3.2h1.2a1.9 1.9 0 0 0 0-3.8H5.1V7.1a1.5 1.5 0 0 1 1.5-1.5h2.6Z"/>',
  tune:
    '<path d="M4.6 7.4h14.8M4.6 12h14.8M4.6 16.6h14.8"/><circle cx="9.2" cy="7.4" r="2"/><circle cx="15" cy="12" r="2"/><circle cx="7.6" cy="16.6" r="2"/>',
  info:
    '<circle cx="12" cy="12" r="8.7"/><path d="M12 11.2v5.4"/><circle cx="12" cy="8.1" r="1" fill="currentColor" stroke="none"/>',
  search:
    '<circle cx="10.6" cy="10.6" r="6"/><path d="M15 15l4.4 4.4"/>',
  back: '<path d="M14.6 5.2 8 12l6.6 6.8"/>',
  close: '<path d="M6.4 6.4l11.2 11.2M17.6 6.4 6.4 17.6"/>',
  // 无边框窗口的自绘标题栏按钮（Win11 的字形：细线，跟系统按钮一个观感）
  minimize: '<path d="M6.2 12.4h11.6"/>',
  maximize: '<rect x="6.6" y="6.6" width="10.8" height="10.8" rx="1.4"/>',
  restore: '<rect x="5.6" y="8.2" width="10.2" height="10.2" rx="1.4"/><path d="M8.8 6.2h8.2a1.2 1.2 0 0 1 1.2 1.2v8.2"/>',
  sync:
    '<path d="M20 12a8 8 0 1 1-2.5-5.8"/><path d="M20.2 4.4v4.2h-4.2"/>',
  folder:
    '<path d="M3.6 6.9A2 2 0 0 1 5.6 4.9h3.5a1.9 1.9 0 0 1 1.5.7l1 1.3h6.8a2 2 0 0 1 2 2v8.2a2 2 0 0 1-2 2h-12.8a2 2 0 0 1-2-2Z"/>',
  download:
    '<path d="M12 4.2v10"/><path d="M8 10.6 12 14.6 16 10.6"/><path d="M4.8 18.8h14.4"/>',
  upload:
    '<path d="M12 19.6V9.4"/><path d="M8 13 12 9l4 4"/><path d="M4.8 5.2h14.4"/>',
  check: '<path d="M5 12.6 9.8 17.4 19 6.6"/>',
  restart:
    '<path d="M4.6 12a7.4 7.4 0 1 0 2.2-5.3"/><path d="M4.4 4.6V9h4.4"/>',
  warning:
    '<path d="M12 4.4 21 19.6H3Z"/><path d="M12 10v4.3"/><circle cx="12" cy="17.1" r="1" fill="currentColor" stroke="none"/>',
  error:
    '<circle cx="12" cy="12" r="8.7"/><path d="M12 7.4v6.2"/><circle cx="12" cy="16.6" r="1" fill="currentColor" stroke="none"/>',
  success:
    '<circle cx="12" cy="12" r="8.7"/><path d="M8.2 12.4 11 15.2 16 9.4"/>',
  clock:
    '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5.4l3.4 2"/>',
  plus: '<path d="M12 5.2v13.6M5.2 12h13.6"/>',
  external:
    '<path d="M13.6 5h5.4v5.4"/><path d="M19 5l-7.6 7.6"/><path d="M18 14v5.2a1.6 1.6 0 0 1-1.6 1.6H5.6A1.6 1.6 0 0 1 4 19.2V8.4a1.6 1.6 0 0 1 1.6-1.6H11"/>',
  shield:
    '<path d="M12 3.6 5.2 6.4v5.8c0 3.9 2.9 6.7 6.8 8.2 3.9-1.5 6.8-4.3 6.8-8.2V6.4Z"/>',
  capsule:
    '<rect x="3.4" y="8" width="17.2" height="8" rx="4"/><path d="M9.4 12h5.2"/>',
  package:
    '<path d="M12 3.6 20.4 8v8L12 20.4 3.6 16V8Z"/><path d="M3.6 8 12 12.4 20.4 8M12 12.4v8"/>',
  home:
    '<path d="M4.4 10.4 12 4.2l7.6 6.2v8.2a1.6 1.6 0 0 1-1.6 1.6H6a1.6 1.6 0 0 1-1.6-1.6Z"/>',
};

/**
 * 生成一个图标元素。
 * @param {string} name ICONS 里的键
 * @param {string} [size] 'i16' | 'i20' | 'i24'
 */
window.iconEl = function (name, size) {
  const wrap = document.createElement("span");
  wrap.className = size || "i20";
  wrap.setAttribute("data-icon", "");
  wrap.setAttribute("aria-hidden", "true");
  wrap.innerHTML =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" ' +
    'stroke-linecap="round" stroke-linejoin="round">' + (window.ICONS[name] || "") + "</svg>";
  return wrap;
};
