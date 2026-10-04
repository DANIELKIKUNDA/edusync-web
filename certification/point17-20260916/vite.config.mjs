export default {
  server: {
    host: '127.0.0.1', port: 55174, strictPort: true,
    proxy: {'/api': 'http://127.0.0.1:58000', '/health': 'http://127.0.0.1:58000'},
  },
};
