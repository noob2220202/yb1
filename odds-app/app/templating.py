from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.services.staking import COMBO_TYPE_LABELS_KO, LEG_RESULT_LABELS_KO, SCENARIO_LABELS_KO

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["scenario_labels"] = SCENARIO_LABELS_KO
templates.env.globals["leg_result_labels"] = LEG_RESULT_LABELS_KO
templates.env.globals["combo_type_labels"] = COMBO_TYPE_LABELS_KO
