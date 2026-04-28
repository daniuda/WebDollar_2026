module.exports = {
  apps: [
    {
      name: 'webd-checkout',
      script: 'server.js',
      cwd: '/var/www/webd-checkout',
      interpreter: 'node',
      env: {
        NODE_URL: 'https://webdollar.io',
        PORT: 3002,
        PAYMENT_TIMEOUT_MS: 600000,
        CORS_ORIGIN: '*',
      },
    },
  ],
};
