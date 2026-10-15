# --- nginx: Basic Auth + статика + прокси на backend ---
FROM nginx:1.27-alpine

# штатный default.conf удаляем: используем свой (Basic Auth + прокси с отключённой буферизацией)
RUN rm -f /etc/nginx/conf.d/default.conf
COPY default.conf /etc/nginx/conf.d/default.conf

# Файл пароля .htpasswd в образ НЕ встраивается: он монтируется из ./nginx/.htpasswd,
# потому что содержит секрет и хранится только на сервере (в git не попадает).
