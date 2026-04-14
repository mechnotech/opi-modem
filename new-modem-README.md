### Если подключен новый телефон/модем

выполни скрипт

```bash
usb-autowarp.sh
```

```bash
service usb-router status
```

лежит тут
(/usr/local/bin/usb-autowarp.sh)


### пароль

cd /opt/opi-modem   # или где лежит проект
ython3 set-password.py                                                                                                                                                                                                                               
   
  Скрипт:                                                                                                                                                                                                                                               
  - Показывает текущий логин                                                                                                                                                                                                                          
  - Берёт новый логин (Enter = оставить старый)
  - Запрашивает пароль через getpass (не отображается в терминале)
  - Требует подтверждение                                                                                                                                                                                                                               
  - Сохраняет в opi-conf.json, не трогая secret_key      