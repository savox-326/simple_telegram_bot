### Простой телеграм-бот для скачивания видео из YouTube
Первостепенной задачей создания этого проекта было обучение по разработке телеграм-ботов, поэтому не ждите от этого проекта высокой отказоустойчивости и отсутствие багов (ооо, их тут, наверно, пруд пруди).
В качестве модуля для скачивания видео был взят популярный [pytube](https://github.com/pytube/pytube)
из-за этого есть ограничение на максимальное разрешение до *720p30fps* включительно. Работает только на системах под управлением Linux, т.к. использует их команды. Протестировано на дистрибутиве Ubuntu, но должен работать и на других. 
Также в проекте реализовано введение истории запросов для каждого пользователя, ее можно отключить, как отдельно, так и для лиц с определенными правами (уровень доступа). 
Для владельца и модераторов доступен расширенный функционал помимо простого скачивания видео, об этом можно узнать в самом коде программы. Кстати о нем, вы часто можете увидеть такую переменную, как **t\_user** - это сокращение от **target\_user**, т.е. целевой пользователь. Информация о целевом пользователе берется из базы данных SQLite, поэтому, это будет не совсем переменная, а список, где **t_user[1]** id пользователя. Еще одна переменная, которую можно встретить в функциях команд это **q**. 
Это также список но в нее передаются о пользовате выполнившим команду. Дело в том, что первоначально я хотел использовать потоки для обращения к базе данных м для них нужно было использовать объект класса **Queue**, поэтому, как сокращение от имени класса переменную назвал **q**. Позже, после многочисленных постов о том, что запросы к SQLite через потоки могут привести к ошибкам, было решено отказаться от этой затеи, но адепт называть так все переменные с данными о выполнившем команду пользователе сохранился. 
У проекта еще присутствует такая проблема, что если кто-либо попытается скачать видео размером где-то больше 100-150 МБ, то данный пользватель навсегда останется в очереди, а его видео так и не будет скачано и отправлено. 
В целом вот и все... ~~добро пожаловать отсюда~~
