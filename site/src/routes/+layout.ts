// Every page is prerendered: the site is served as static files, so nothing
// can be rendered on request.
export const prerender = true;
// Pages serves /about/ as about/index.html. Always emitting the trailing slash
// keeps links, prerendered files and the URLs Pages answers in agreement.
export const trailingSlash = 'always';
