# 配置構成

Client Browser から HTTPS で Apache HTTP Server に接続する。
Apache HTTP Server は application context /card-enrollment を reverse proxy で Tomcat に転送する。
Tomcat は JDBC で PostgreSQL に接続する。
Tomcat から external service connections を使用する。
