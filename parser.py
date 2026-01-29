import gitlab
from typing import Dict, Any, Optional, List
import logging
from config import GITLAB_URL

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

gitlab_clients = {}


def init_gitlab_client(chat_id: int, gitlab_token: str) -> Optional[gitlab.Gitlab]:
    try:
        if not gitlab_token or gitlab_token == 'ВАШ_GITLAB_TOKEN_ЗДЕСЬ':
            logger.error(f"Невалидный GitLab токен для chat_id: {chat_id}")
            return None

        gl = gitlab.Gitlab(
            url=GITLAB_URL,
            private_token=gitlab_token
        )
        gl.auth()
        gitlab_clients[chat_id] = gl
        logger.info(f"GitLab клиент инициализирован для chat_id: {chat_id}")
        return gl
    except gitlab.exceptions.GitlabAuthenticationError:
        logger.error(f"Ошибка аутентификации GitLab для chat_id {chat_id}")
        return None
    except Exception as e:
        logger.error(f"Ошибка инициализации GitLab для chat_id {chat_id}: {e}")
        return None


def get_gitlab_client(chat_id: int) -> Optional[gitlab.Gitlab]:
    if chat_id in gitlab_clients:
        return gitlab_clients[chat_id]
    return None


def get_last_pipeline(chat_id: int, project_id: int) -> Optional[Dict[str, Any]]:
    try:
        gl = get_gitlab_client(chat_id)
        if not gl:
            logger.error(f"GitLab клиент не инициализирован для chat_id: {chat_id}")
            return None

        project = gl.projects.get(project_id)
        pipelines = project.pipelines.list(get_all=True, per_page=1)

        if not pipelines:
            return None

        pipeline = pipelines[0]
        full_pipeline = project.pipelines.get(pipeline.id)
        jobs = full_pipeline.jobs.list(get_all=True, per_page=100)

        stages = {}
        for job in jobs[::-1]:
            stage = job.stage
            if stage not in stages:
                stages[stage] = []
            stages[stage].append(job)

        pipeline_info = {
            'id': pipeline.id,
            'status': pipeline.status,
            'ref': pipeline.ref,
            'created_at': pipeline.created_at,
            'duration': full_pipeline.duration or 0,
            'web_url': pipeline.web_url,
            'sha': pipeline.sha[:8] if pipeline.sha else '',
            'stages': {}
        }

        for stage_name, stage_jobs in stages.items():
            statuses = [job.status for job in stage_jobs]
            pipeline_info['stages'][stage_name] = {
                'summary': {
                    'total': len(stage_jobs),
                    'success': statuses.count('success'),
                    'failed': statuses.count('failed'),
                    'running': statuses.count('running'),
                    'pending': statuses.count('pending'),
                }
            }

        return pipeline_info

    except gitlab.exceptions.GitlabGetError as e:
        if "404" in str(e):
            logger.error(f"Проект {project_id} не найден для chat_id {chat_id}")
        else:
            logger.error(f"GitLab ошибка при получении пайплайна для chat_id {chat_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении пайплайна для chat_id {chat_id}: {e}")
        return None


def safe_format(text: str) -> str:
    if not text:
        return ""

    # TODO: switch to HTML
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '=', '-', '|', '{', '}', '!']

    for char in special_chars:
        text = text.replace(char, f'\\{char}')

    return text


def format_pipeline_message(pipeline_info: Dict[str, Any]) -> str:
    if not pipeline_info:
        return "❌ Не удалось получить информацию о пайплайне"

    pipeline_id = safe_format(str(pipeline_info.get('id', 'N/A')))
    status = safe_format(pipeline_info.get('status', 'N/A'))
    ref = safe_format(pipeline_info.get('ref', 'N/A'))
    created_at = safe_format(pipeline_info.get('created_at', 'N/A'))
    duration = safe_format(str(pipeline_info.get('duration', 'N/A')))
    sha = safe_format(pipeline_info.get('sha', 'N/A'))
    web_url = pipeline_info.get('web_url', '#')

    message = f"🚀 *Pipeline #{pipeline_id}*\n\n"
    message += f"*Status:* {status}\n"
    message += f"*Branch:* `{ref}`\n"
    message += f"*Created:* {created_at}\n"
    message += f"*Duration:* {duration} sec\n"
    message += f"*SHA:* `{sha}`\n\n"

    stages = pipeline_info.get('stages', {})
    if stages:
        message += "*Stages:*\n"
        for stage_name, stage_data in stages.items():
            safe_stage_name = safe_format(stage_name)
            summary = stage_data.get('summary', {})
            message += f"*{safe_stage_name.upper()}*\n"
            message += f"  ✅ Success: {summary.get('success', 0)}\n"
            message += f"  ❌ Failed: {summary.get('failed', 0)}\n"
            message += f"  🔄 Running: {summary.get('running', 0)}\n"
            message += f"  ⏳ Pending: {summary.get('pending', 0)}\n\n"

    message += f"🔗 [Open pipeline]({web_url})"
    return message


def get_second_last_mr_details(chat_id: int, project_id: int) -> str:
    try:
        gl = get_gitlab_client(chat_id)
        if not gl:
            logger.error(f"GitLab клиент не инициализирован для chat_id: {chat_id}")
            return "❌ GitLab client not initialized"

        project = gl.projects.get(project_id)

        all_mrs = project.mergerequests.list(
            state='all',
            get_all=True,
            sort='desc',
            order_by='created_at',
            per_page=50
        )

        if len(all_mrs) < 2:
            return "❌ Not enough MRs found"

        second_last_mr = all_mrs[0]
        mr = project.mergerequests.get(second_last_mr.iid)

        mr_iid = safe_format(str(mr.iid))
        mr_title = safe_format(mr.title)
        author = safe_format(mr.author['username'])
        source_branch = safe_format(mr.source_branch)
        target_branch = safe_format(mr.target_branch)
        created_at = safe_format(mr.created_at)
        updated_at = safe_format(mr.updated_at)

        result = f"📋 *MR {mr_iid}*\n\n"
        result += f"*Title:* {mr_title}\n"
        result += f"*Author:* {author}\n"
        result += f"*Status:* {get_mr_status_icon(mr.state)} {mr.state.upper()}\n"
        result += f"*Branch:* `{source_branch}` → `{target_branch}`\n"
        # result += f"*Created:* {created_at}\n"
        # result += f"*Updated:* {updated_at}\n"

        if hasattr(mr, 'reviewers') and mr.reviewers:
            reviewers = [safe_format(r['username']) for r in mr.reviewers]
            result += f"*Reviewers:* {', '.join(reviewers)}\n"

        if mr.labels:
            safe_labels = [safe_format(label) for label in mr.labels]
            result += f"*Labels:* {', '.join(safe_labels)}\n"

        notes = mr.notes.list(get_all=True)

        if notes:
            reviewer_comments = []
            for note in notes:
                if getattr(note, 'system', False):
                    continue
                if note.author['id'] == mr.author['id']:
                    continue
                reviewer_comments.append(note)

            if reviewer_comments:
                result += f"\n💬 *Comments:*"

                comments_by_reviewer = {}
                for note in reviewer_comments:
                    reviewer_name = safe_format(f'{note.author['name']} - {note.author['username']}')
                    if reviewer_name not in comments_by_reviewer:
                        comments_by_reviewer[reviewer_name] = []
                    comments_by_reviewer[reviewer_name].append(note)

                for reviewer, comments in comments_by_reviewer.items():
                    result += f"\n👤 *{reviewer}*:\n"

                    for i, note in enumerate(comments, 1):
                        if note.body:
                            clean_body = safe_format(' '.join(note.body.strip().split()))
                            if "Score for the group is:" in clean_body:
                                score_text = clean_body[clean_body.find("Score for the group is:"):]
                                score_text = score_text[-50:] if len(score_text) > 50 else score_text
                                result += f"  {score_text}\n"
                            else:
                                if len(clean_body) > 200:
                                    if clean_body.find('Score for all previous groups together:') \
                                            and clean_body.find('Preliminary correctness:'):
                                        score_all_index = clean_body.find('Score for all previous groups together:')
                                        score_per_index = clean_body.find('Preliminary correctness:')
                                        if clean_body[score_all_index:score_all_index + 46] not in result:
                                            result += f"{clean_body[score_all_index:score_all_index + 46]}\n"
                                        if clean_body[score_per_index:score_per_index + 31] not in result:
                                            result += f"{clean_body[score_per_index:score_per_index + 31]}\n"
                                    else:
                                        result += f"  {clean_body[:300]}...\n"
                                else:
                                    result += f"  {clean_body}\n"
            else:
                result += "\n💬 *Reviewer comments:*\n  No comments from reviewers\n"
        else:
            result += "\n💬 *Reviewer comments:*\n  No comments\n"

        result += f"\n🔗 [Open MR]({mr.web_url})"

        return result

    except gitlab.exceptions.GitlabGetError as e:
        if "404" in str(e):
            logger.error(f"Проект {project_id} не найден для chat_id {chat_id}")
            return "❌ Project not found"
        else:
            logger.error(f"GitLab ошибка при получении MR для chat_id {chat_id}: {e}")
            return f"❌ GitLab error: {str(e)[:200]}"
    except Exception as e:
        logger.error(f"Error getting MR for chat_id {chat_id}: {e}")
        return f"❌ Error: {str(e)[:200]}"


def get_mr_status_icon(state: str) -> str:
    icons = {
        'opened': '🟢',
        'merged': '🟣',
        'closed': '🔴'
    }
    return icons.get(state, '⚪')


def test_gitlab_connection(chat_id: int, gitlab_token: str) -> tuple[bool, str]:
    try:
        gl = gitlab.Gitlab(
            url=GITLAB_URL,
            private_token=gitlab_token
        )
        gl.auth()
        user = gl.user
        return True, f"✅ Подключение успешно\nUser: {user.username}"
    except gitlab.exceptions.GitlabAuthenticationError:
        return False, "❌ Ошибка аутентификации: неверный токен"
    except Exception as e:
        return False, f"❌ Ошибка подключения: {str(e)}"
