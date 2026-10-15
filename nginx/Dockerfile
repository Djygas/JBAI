# --- nginx: Basic Auth + статика + прокси на backend ---
FROM nginx:1.27-alpine

RUN rm -f /etc/nginx/conf.d/default.conf
COPY default.conf /etc/nginx/conf.d/default.conf

# .htpasswd НЕ попадает в образ: файл монтируется из ./nginx/.htpasswd (он в .gitignore)
RUN test -f /etc/nginx/mime.types
