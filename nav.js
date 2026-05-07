(function () {
  var H = 42;
  var LINKS = [
    { label: 'Explorer',  path: '/' },
    { label: 'Miner',     path: '/wdexperience/' },
    { label: 'Staking',   path: '/webd-staking/' },
    { label: 'DEX',       path: '/webd-dex/' },
    { label: 'Checkout',  path: '/webd-checkout/' },
  ];

  function isActive(path) {
    var p = window.location.pathname;
    return path === '/' ? p === '/' : p.startsWith(path);
  }

  var css = document.createElement('style');
  css.textContent = [
    '#_wn{position:fixed;top:0;left:0;right:0;z-index:2147483647;',
    'height:' + H + 'px;background:#0f1117;border-bottom:1px solid #2d3148;',
    'display:flex;align-items:center;padding:0 16px;gap:2px;',
    'font-family:"Segoe UI",system-ui,sans-serif;font-size:13px;',
    'box-sizing:border-box;}',
    '#_wn .wn-logo{color:#a78bfa;font-weight:700;font-size:14px;',
    'margin-right:10px;text-decoration:none;white-space:nowrap;letter-spacing:-.3px;}',
    '#_wn a{color:#64748b;text-decoration:none;padding:5px 11px;',
    'border-radius:6px;transition:color .12s,background .12s;white-space:nowrap;}',
    '#_wn a:hover{color:#e2e8f0;background:#1a1d2e;}',
    '#_wn a.wn-active{color:#a78bfa;background:#1a1d2e;font-weight:600;}',
    'body{padding-top:' + H + 'px!important;}',
  ].join('');
  document.head.appendChild(css);

  var nav = document.createElement('nav');
  nav.id = '_wn';

  var logo = document.createElement('a');
  logo.className = 'wn-logo';
  logo.href = '/';
  logo.textContent = '◆ WebDollar';
  nav.appendChild(logo);

  var sep = document.createElement('span');
  sep.style.cssText = 'flex:1';
  nav.appendChild(sep);

  LINKS.forEach(function (lnk) {
    var a = document.createElement('a');
    a.href = lnk.path;
    a.textContent = lnk.label;
    if (isActive(lnk.path)) a.className = 'wn-active';
    nav.appendChild(a);
  });

  if (document.body) {
    document.body.insertBefore(nav, document.body.firstChild);
  } else {
    document.addEventListener('DOMContentLoaded', function () {
      document.body.insertBefore(nav, document.body.firstChild);
    });
  }
})();
