#!/usr/bin/env python
# -*- coding: utf-8 -*-

#    Copyright 2010, 2011 C Sommer, C Straehle, U Koethe, FA Hamprecht. All rights reserved.
#    
#    Redistribution and use in source and binary forms, with or without modification, are
#    permitted provided that the following conditions are met:
#    
#       1. Redistributions of source code must retain the above copyright notice, this list of
#          conditions and the following disclaimer.
#    
#       2. Redistributions in binary form must reproduce the above copyright notice, this list
#          of conditions and the following disclaimer in the documentation and/or other materials
#          provided with the distribution.
#    
#    THIS SOFTWARE IS PROVIDED BY THE ABOVE COPYRIGHT HOLDERS ``AS IS'' AND ANY EXPRESS OR IMPLIED
#    WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
#    FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE ABOVE COPYRIGHT HOLDERS OR
#    CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
#    CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
#    SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
#    ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
#    NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
#    ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#    
#    The views and conclusions contained in the software and documentation are those of the
#    authors and should not be interpreted as representing official policies, either expressed
#    or implied, of their employers.

from PyQt4.QtCore import QRect, QRectF, QTimer
from PyQt4.QtGui import QGraphicsScene, QImage
from OpenGL.GL import *

from patchAccessor import PatchAccessor
from imageSceneRenderer import ImageSceneRenderer

class ImagePatch(object):    
    def __init__(self, rectF):
        assert(type(rectF) == QRectF)
        
        self.rectF  = rectF
        self.rect   = QRect(round(rectF.x()),     round(rectF.y()), \
                            round(rectF.width()), round(rectF.height()))
        self._image  = QImage(self.rect.width(), self.rect.height(), QImage.Format_RGB888)
        self.texture = -1
        self.dirty = True

    @property
    def height(self):
        return self.rect.height()
    
    @property
    def width(self):
        return self.rect.width()

    def drawTexture(self):
        tx = self.rect.x()
        ty = self.rect.y()
        w = self.rect.width()
        h = self.rect.height()
        glBindTexture(GL_TEXTURE_2D, self.texture)
        glBegin(GL_QUADS)
        glTexCoord2f(0.0, 1.0)
        glVertex2f(tx, ty)
        glTexCoord2f(1.0, 1.0)
        glVertex2f(tx + w, ty)
        glTexCoord2f(1.0, 0.0)
        glVertex2f(tx + w, ty + h)
        glTexCoord2f(0.0, 0.0)
        glVertex2f(tx, ty + h)
        glEnd()

    @property
    def image(self):
        return self._image
    
    @image.setter
    def image(self, img):
        self._image = img
        self.dirty = False

class ImageScene2D(QGraphicsScene):
    blockSize = 64
    glUpdateDelay = 10 #update delay when a new patch arrives in ms
    
    @property
    def useGL(self):
        return self._glWidget is not None
    
    def __init__(self, shape2D, glWidget = None):
        QGraphicsScene.__init__(self)
        self._glWidget = glWidget
        self._useGL = (glWidget != None)
        self._shape2D = shape2D
        self._updatableTiles = []
        
        self.imagePatches   = []
        patchAccessor = PatchAccessor(*self._shape2D, blockSize=self.blockSize)

        for i in range(patchAccessor.patchCount):
            r = patchAccessor.patchRectF(i)
            patch = ImagePatch(r)
            self.imagePatches.append(patch)
        
        self.setSceneRect(0,0, *self._shape2D)
    
        self._imageSceneRenderer = ImageSceneRenderer(self.imagePatches, self._glWidget)
        self._imageSceneRenderer._thread.patchAvailable.connect(self.updatePatch)

    def updatePatch(self, patchNr):
        p = self.imagePatches[patchNr]
        self._updatableTiles.append(patchNr)
        
        #print "update patch %d" % (patchNr)
        if self._useGL:
            QTimer.singleShot(self.glUpdateDelay, self.update)
        else:
            self.invalidate(p.rectF, QGraphicsScene.BackgroundLayer)

    def drawBackgroundSoftware(self, painter, rect):
        drawnTiles = 0
        for i,patch in enumerate(self.imagePatches):
            if patch.dirty or not patch.rectF.intersect(rect): continue
            painter.drawImage(patch.rectF.topLeft(), patch.image)
            drawnTiles +=1
        #print "ImageView2D.drawBackgroundSoftware: drew %d of %d tiles" % (drawnTiles, len(self.imagePatches))

    def markTilesDirty(self):
        for patch in self.imagePatches:
            patch.dirty = True
    
    def initializeGL(self):
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_TEXTURE_2D)
        glClearColor(0.0, 0.0, 0.0, 0.0);
        glClear(GL_COLOR_BUFFER_BIT)

    def drawBackgroundGL(self, painter, rect):
        #update the textures of those patches that were updated
        for t in self._updatableTiles:
            patch = self.imagePatches[t]
            if patch.texture > -1:
                self._glWidget.deleteTexture(patch.texture)
            patch.texture = self._glWidget.bindTexture(patch.image)
            #see 'backingstore' example by Ariya Hidayat
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            #this ensures a seamless transition between tiles
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        self._updatableTiles = []
        
        painter.beginNativePainting()
        #This will clear the screen, but also introduce flickering
        glClearColor(0.0, 1.0, 0.0, 1.0);
        glClear(GL_COLOR_BUFFER_BIT);
        
        drawnTiles = 0
        for i, patch in enumerate(self.imagePatches):
            if patch.dirty or not patch.rectF.intersect(rect): continue
            
            patch.drawTexture()
            drawnTiles +=1
            
        def drawRect(x1, y1, w, h):
            x1 = float(s.x()); y1 = float(s.y())
            x2 = float(x1+w);  y2 = float(y1+h)
            glRectd(x1, y1, x2, y2)
        #  ************************************************
        #  * rectangle s                                  *
        #  *                                              *
        #  *             ***************************      *                   
        #  *             * rectangle r             *      *
        #  *             ***************************      *                   
        #  *                                              *                 
        #  ************************************************
         
        #r = QRectF(0,0,*self._shape2D)
        #s = rect
        #print rect            
        ##to clear the viewport, we would need sth. like this, crashes atm.
        #glColor3f(0.0, 0.0, 1.0)
        #if s.left() < r.left():
        #    drawRect(s.x(), s.y(), r.left()-s.left(), s.height())
        #if s.top() < r.top():
        #    drawRect(r.x(), s.y(), r.width(), r.top()-s.top())
        #if s.bottom()>r.bottom():
        #    drawRect(r.left(), r.bottom(), r.width(), r.height())
        #if s.right()<r.right():
        #    drawRect(s.x(), s.y(), s.width()-r.width(), s.height())

        painter.endNativePainting()
        #print "ImageView2D.drawBackgroundGL: drew %d of %d tiles" % (drawnTiles, len(self.imagePatches))

    def drawBackground(self, painter, rect):
        if self.useGL:
            self.drawBackgroundGL(painter, rect)
        else:
            self.drawBackgroundSoftware(painter, rect)