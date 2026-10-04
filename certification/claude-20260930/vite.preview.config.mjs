// Serves the production build (frontend/dist) and proxies the API to the isolated certification API.
export default {
  preview: {
    host: '127.0.0.1', port: 55175, strictPort: true,
    proxy: {'/api': 'http://127.0.0.1:58100', '/health': 'http://127.0.0.1:58100'},
  },
};
