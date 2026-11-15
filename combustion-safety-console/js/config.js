/* CONFIG: where the backend API lives. Change apiBase, or open any page with ?api=http://host:port to override it. */
window.CSC_CONFIG={apiBase:new URLSearchParams(location.search).get("api")||"http://localhost:5000"};
