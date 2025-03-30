import zeep
import logging
import traceback
from loguru import logger

from post import Post

class MlgManager:
    batch_size = 200

    def __init__(self, username, password, wsdl):
        self.username = username
        self.password = password
        try:
            self.client = zeep.Client(wsdl=wsdl)
            logger.info(f"Инициализация Медиалогии: WSDL {wsdl}")
        except Exception as e:
            logger.error(f"Ошибка инициализации клиента Медиалогии: {e}")
            logger.error(traceback.format_exc())
            raise

    def call_api(self, method_name, **kwargs):
        try:
            method = getattr(self.client.service, method_name)
            logger.info(f"Вызов метода {method_name} с параметрами: {kwargs}")
            
            reply = method(**kwargs)
            
            # Проверка наличия ошибки через hasattr вместо get
            if hasattr(reply, 'Error') and reply.Error is not None:
                logger.error(f"Ошибка в ответе API: {reply.Error}")
                raise RuntimeError(f"API Error: {reply.Error}")
            
            return reply
        except Exception as e:
            logger.error(f"Ошибка при вызове метода {method_name}: {e}")
            logger.error(traceback.format_exc())
            raise

    def get_posts(self, report_id, date_from, date_to, page=1):
        logger.info(f"Получение постов: report_id={report_id}, date_from={date_from}, date_to={date_to}")
        
        try:
            posts = self.get_posts_page(report_id, date_from, date_to, page, self.batch_size)
            
            logger.info(f"Получено постов на первой странице: {len(posts)}")
            
            if len(posts) == self.batch_size:
                logger.info("Загрузка следующих страниц...")
                posts += self.get_posts(report_id, date_from, date_to, page + 1)

            return posts
        except Exception as e:
            logger.error(f"Ошибка получения постов: {e}")
            logger.error(traceback.format_exc())
            return []

    def get_posts_page(self, report_id, date_from, date_to, page_index, page_size=None):
        if not page_size:
            page_size = self.batch_size
        
        logger.info(f"Получение страницы {page_index} по {page_size} постов")
        
        try:
            reply = self.call_api(
                "GetPosts",
                credentials={"Login": self.username, "Password": self.password},
                reportId=report_id,
                dateFrom=date_from,
                dateTo=date_to,
                pageIndex=page_index,
                pageSize=page_size,
            )

            # Обработка ответа с учетом структуры Zeep
            cubus_posts = getattr(reply.Posts, 'CubusPost', []) if hasattr(reply, 'Posts') else []
            
            logger.info(f"Получено постов на странице {page_index}: {len(cubus_posts)}")
            
            return Post.parse_posts(cubus_posts)
        except Exception as e:
            logger.error(f"Ошибка получения страницы постов: {e}")
            logger.error(traceback.format_exc())
            return []

    def get_n_posts(self, report_id, date_from, date_to):
        try:
            reply = self.call_api(
                "GetPostsStatsByDate",
                credentials={"Login": self.username, "Password": self.password},
                reportId=report_id,
                dateFrom=date_from,
                dateTo=date_to,
            )

            # Обработка с учетом структуры Zeep
            count = sum(
                entry.PostsCount
                for entry in getattr(reply.Entries, 'CubusDateStats', [])
            )
            
            logger.info(f"Количество постов: {count}")
            return count
        except Exception as e:
            logger.error(f"Ошибка подсчета постов: {e}")
            logger.error(traceback.format_exc())
            return 0