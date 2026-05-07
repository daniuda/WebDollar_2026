(function () {
  var H = 44;
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
    'height:' + H + 'px;',
    'background:linear-gradient(135deg,#0f1117 0%,#1a1040 100%);',
    'border-bottom:1px solid rgba(167,139,250,0.2);',
    'display:flex;align-items:center;padding:0 18px;gap:2px;',
    'font-family:"Segoe UI",system-ui,sans-serif;font-size:13px;',
    'box-sizing:border-box;}',
    '#_wn .wn-logo{color:#a78bfa;font-weight:700;font-size:15px;',
    'margin-right:12px;text-decoration:none;white-space:nowrap;letter-spacing:-.3px;',
    'text-shadow:0 0 18px rgba(167,139,250,0.6),0 0 40px rgba(167,139,250,0.2);}',
    '#_wn a{color:#cbd5e1;text-decoration:none;padding:5px 12px;',
    'border-radius:6px;transition:color .15s,background .15s;white-space:nowrap;}',
    '#_wn a:hover{color:#f1f5f9;background:rgba(167,139,250,0.15);}',
    '#_wn a.wn-active{color:#a78bfa;background:rgba(167,139,250,0.18);font-weight:600;',
    'text-shadow:0 0 12px rgba(167,139,250,0.4);}',
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
