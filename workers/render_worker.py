from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal

from model.project import Project
from rendering.renderer import HairRenderer

class RenderSignals(QObject):
    """Signals emitted by a render worker back to the GUI thread."""
    finished=Signal(int,str,object,object)
    error=Signal(int,str)

class RenderJob(QRunnable):
    """Render one card or an entire sheet without blocking Qt's event loop."""
    def __init__(self,generation:int,mode:str,project:Project,card_index,supersample:int):
        super().__init__()
        self.generation=generation; self.mode=mode; self.project=project; self.card_index=card_index; self.supersample=max(1,int(supersample)); self.signals=RenderSignals()
    def run(self):
        try:
            renderer=HairRenderer(self.supersample)
            if self.mode=="card":
                card=self.project.cards[self.card_index]
                cell_w=self.project.width//self.project.columns; cell_h=self.project.height//self.project.rows
                col=self.card_index%self.project.columns; row=self.card_index//self.project.columns
                width=cell_w if col<self.project.columns-1 else self.project.width-col*cell_w
                height=cell_h if row<self.project.rows-1 else self.project.height-row*cell_h
                image=renderer.render_card(card.style,width,height,card.seed)
            else:
                image=renderer.render_sheet(self.project); self.card_index=-1
            self.signals.finished.emit(self.generation,self.mode,self.card_index,image)
        except Exception as exc:
            self.signals.error.emit(self.generation,f"{type(exc).__name__}: {exc}")
