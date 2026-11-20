"""在旧入口提供相同的 WebUI 钩子规则。"""

from app.utils.common.log.hooks import (
    HOOK_TYPE_DROP as HOOK_TYPE_DROP,
)
from app.utils.common.log.hooks import (
    HOOK_TYPE_REPLACE as HOOK_TYPE_REPLACE,
)
from app.utils.common.log.hooks import (
    SUPPORTED_HOOK_TYPES as SUPPORTED_HOOK_TYPES,
)
from app.utils.common.log.hooks import (
    LineHook as LineHook,
)
from app.utils.common.log.hooks import (
    LogHook as LogHook,
)
from app.utils.common.log.hooks import (
    apply_hooks as apply_hooks,
)
from app.utils.common.log.hooks import (
    compile_hook as compile_hook,
)
from app.utils.common.log.hooks import (
    load_hooks as load_hooks,
)
from app.utils.common.log.hooks import (
    make_line_hook as make_line_hook,
)
from app.utils.common.log.hooks import (
    validate_hook as validate_hook,
)
