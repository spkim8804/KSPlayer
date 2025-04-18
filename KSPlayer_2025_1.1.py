import sys
import cv2
import numpy as np
import os
import csv
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QListWidget, QLabel, QPushButton, 
                           QFileDialog, QGroupBox, QSlider, QSpinBox, QTextEdit,
                           QMessageBox, QComboBox)
from PyQt5.QtCore import Qt, QTimer, QMimeData, QUrl, QPoint
from PyQt5.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QMouseEvent

class VideoListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDrop)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event):
        urls = event.mimeData().urls()
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv']
        
        for url in urls:
            file_path = url.toLocalFile()
            if any(file_path.lower().endswith(ext) for ext in video_extensions):
                self.addItem(file_path)
            
    def keyPressEvent(self, event):
        if event.key() in [Qt.Key_Delete, Qt.Key_Backspace]:
            # Get selected items
            selected_items = self.selectedItems()
            if selected_items:
                # Remove selected items
                for item in selected_items:
                    self.takeItem(self.row(item))
        else:
            super().keyPressEvent(event)

class CustomSlider(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setMinimumHeight(20)
        self.setMouseTracking(True)
        self.dragging = False
        self.current_frame = 0
        self.frame_count = 0
        
    def set_frame_count(self, count):
        self.frame_count = count
        
    def set_current_frame(self, frame):
        self.current_frame = frame
        self.update()
        
    def paintEvent(self, event):
        if self.frame_count == 0:
            return
            
        painter = QPainter(self)
        width = self.width()
        height = self.height()
        
        # Draw background
        painter.fillRect(0, 0, width, height, Qt.white)
        
        # Calculate frame width
        frame_width = width / (self.frame_count - 1)
        
        # Draw current frame indicator
        if self.current_frame < self.frame_count:
            x = int(self.current_frame * frame_width)
            painter.setPen(QPen(Qt.black, 2))
            painter.drawLine(x, 0, x, height)
            
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.update_frame_from_mouse(event)
            
    def mouseMoveEvent(self, event):
        if self.dragging:
            self.update_frame_from_mouse(event)
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            
    def update_frame_from_mouse(self, event):
        width = self.width()
        frame_width = width / (self.frame_count - 1)
        frame = int(event.x() / frame_width)
        frame = max(0, min(frame, self.frame_count - 1))
        if frame != self.current_frame:
            self.current_frame = frame
            self.parent.cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
            self.parent.update_frame()
            self.update()

class AnnotationBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(20)
        self.frame_count = 0
        self.zone_array = None
        
    def set_frame_count(self, count):
        self.frame_count = count
        
    def set_zone_array(self, array):
        self.zone_array = array
        self.update()
        
    def paintEvent(self, event):
        if self.frame_count == 0 or self.zone_array is None:
            return
            
        painter = QPainter(self)
        width = self.width()
        height = self.height()
        
        # Draw background
        painter.fillRect(0, 0, width, height, Qt.white)
        
        # Calculate frame width
        frame_width = width / (self.frame_count - 1)
        
        # Draw zone colors
        for i in range(self.frame_count):
            x = int(i * frame_width)
            if self.zone_array[i] == 1:  # Zone A
                painter.fillRect(x, 0, int(frame_width) + 1, height, QColor(255, 0, 0))  # Red
            elif self.zone_array[i] == 2:  # Zone B
                painter.fillRect(x, 0, int(frame_width) + 1, height, QColor(0, 0, 255))  # Blue

class MouseBehaviorAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mouse Behavior Analyzer")
        self.setGeometry(100, 100, 1200, 800)
        self.setAcceptDrops(True)  # Enable drag and drop for main window
        
        # Variables for video playback
        self.video_path = None
        self.cap = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.frame_count = 0
        self.current_frame = 0
        self.playback_speed = 1.0
        self.is_updating_slider = False  # Flag to prevent recursive updates
        
        # Variables for behavior analysis
        self.mouse_count = 1  # Default number of mice
        self.current_mouse = 0  # Currently selected mouse (0-based index)
        self.zone_arrays = None  # List of zone arrays for each mouse
        self.current_zone = None
        self.is_counting = False
        self.mouse_pressed = False  # Track if mouse button is pressed
        
        self.init_ui()
        
    def init_ui(self):
        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout()
        
        # Left panel - File list
        left_panel = QGroupBox("File List")
        left_layout = QVBoxLayout()
        
        self.file_list = QListWidget()
        self.file_list.itemDoubleClicked.connect(self.load_video)
        self.file_list.setAcceptDrops(True)
        self.file_list.setDragDropMode(QListWidget.DragDrop)
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)
        
        # Set up drag and drop for file list
        self.file_list.dragEnterEvent = self.file_list_drag_enter_event
        self.file_list.dropEvent = self.file_list_drop_event
        
        # Set up key press event for file list
        self.file_list.keyPressEvent = self.file_list_key_press_event
        
        load_btn = QPushButton("Load Files")
        load_btn.clicked.connect(self.load_files)
        
        left_layout.addWidget(load_btn)
        left_layout.addWidget(self.file_list)
        left_panel.setLayout(left_layout)
        left_panel.setFixedWidth(300)
        
        # Center panel - Video display
        center_panel = QGroupBox("Video")
        center_layout = QVBoxLayout()
        
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(640, 480)
        
        # Custom slider and annotation bar
        slider_layout = QVBoxLayout()
        
        # Custom slider
        self.custom_slider = CustomSlider(self)
        self.custom_slider.setMinimumHeight(20)
        slider_layout.addWidget(self.custom_slider)
        
        # Annotation bar
        self.annotation_bar = AnnotationBar(self)
        self.annotation_bar.setMinimumHeight(20)
        slider_layout.addWidget(self.annotation_bar)
        
        # Current time display
        self.time_label = QLabel("0:00 / 0:00")
        slider_layout.addWidget(self.time_label)
        
        # Speed control
        speed_layout = QHBoxLayout()
        speed_label = QLabel("Playback Speed:")
        self.speed_spinbox = QSpinBox()
        self.speed_spinbox.setRange(1, 500)
        self.speed_spinbox.setValue(100)
        self.speed_spinbox.setSuffix("%")
        self.speed_spinbox.valueChanged.connect(self.speed_changed)
        speed_layout.addWidget(speed_label)
        speed_layout.addWidget(self.speed_spinbox)
        
        # Control buttons
        control_layout = QHBoxLayout()
        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self.toggle_play)
        self.delete_mode_btn = QPushButton("Delete Mode")
        self.delete_mode_btn.setCheckable(True)
        self.delete_mode_btn.clicked.connect(self.toggle_delete_mode)
        self.delete_all_btn = QPushButton("Delete All")
        self.delete_all_btn.clicked.connect(self.delete_all_labels)
        control_layout.addWidget(self.play_btn)
        control_layout.addWidget(self.delete_mode_btn)
        control_layout.addWidget(self.delete_all_btn)
        
        center_layout.addWidget(self.video_label)
        center_layout.addLayout(slider_layout)
        center_layout.addLayout(speed_layout)
        center_layout.addLayout(control_layout)
        center_panel.setLayout(center_layout)
        
        # Right panel - Analysis
        right_panel = QGroupBox("Analysis")
        right_layout = QVBoxLayout()
        
        # Mouse count selection
        mouse_count_layout = QHBoxLayout()
        mouse_count_label = QLabel("Number of Mice:")
        self.mouse_count_combo = QComboBox()
        self.mouse_count_combo.addItems([str(i) for i in range(1, 11)])
        self.mouse_count_combo.currentTextChanged.connect(self.mouse_count_changed)
        mouse_count_layout.addWidget(mouse_count_label)
        mouse_count_layout.addWidget(self.mouse_count_combo)
        right_layout.addLayout(mouse_count_layout)
        
        # Mouse selection
        mouse_select_layout = QHBoxLayout()
        mouse_select_label = QLabel("Select Mouse:")
        self.mouse_select_combo = QComboBox()
        self.mouse_select_combo.currentIndexChanged.connect(self.mouse_selection_changed)
        mouse_select_layout.addWidget(mouse_select_label)
        mouse_select_layout.addWidget(self.mouse_select_combo)
        right_layout.addLayout(mouse_select_layout)
        
        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)
        self.analysis_text.setMinimumHeight(200)
        
        instruction_label = QLabel("Controls:\nLeft Click: Zone A\nRight Click: Zone B\n"
                                 "Delete Mode: Click to delete annotation")
        
        right_layout.addWidget(self.analysis_text)
        right_layout.addWidget(instruction_label)
        right_panel.setLayout(right_layout)
        right_panel.setFixedWidth(200)
        
        # Add panels to main layout
        layout.addWidget(left_panel)
        layout.addWidget(center_panel)
        layout.addWidget(right_panel)
        
        main_widget.setLayout(layout)
        
        # Set up key and mouse event handling
        self.setFocusPolicy(Qt.StrongFocus)
        self.video_label.mousePressEvent = self.mouse_press_event
        self.video_label.mouseReleaseEvent = self.mouse_release_event
        
    def load_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Load Videos", "", 
                                              "Video Files (*.mp4 *.avi *.mov *.mkv *.wmv, *.mpg)")
        for file in files:
            # Check if file already exists in the list
            if not any(self.file_list.item(i).text() == file for i in range(self.file_list.count())):
                self.file_list.addItem(file)
                
    def load_video(self, item):
        self.video_path = item.text()
        if self.cap is not None:
            self.cap.release()
        self.cap = cv2.VideoCapture(self.video_path)
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Try to load existing CSV file from the same directory
        video_dir = os.path.dirname(self.video_path)
        video_name = os.path.splitext(os.path.basename(self.video_path))[0]
        csv_path = os.path.join(video_dir, f"{video_name}.csv")
        
        if os.path.exists(csv_path):
            try:
                with open(csv_path, 'r') as csvfile:
                    reader = csv.reader(csvfile)
                    header = next(reader)  # Get header
                    
                    # Find mouse columns and determine number of mice in CSV
                    mouse_columns = []
                    for i, col in enumerate(header):
                        if col.startswith('Mouse'):
                            try:
                                mouse_num = int(col.split(' ')[1])
                                mouse_columns.append((i, mouse_num))
                            except (IndexError, ValueError):
                                continue
                    
                    if mouse_columns:
                        # Sort by mouse number
                        mouse_columns.sort(key=lambda x: x[1])
                        max_mouse_num = mouse_columns[-1][1]
                        
                        # Update mouse count to match CSV file
                        self.mouse_count = max_mouse_num
                        self.mouse_count_combo.setCurrentText(str(max_mouse_num))
                        
                        # Initialize zone arrays with correct mouse count
                        self.initialize_zone_arrays()
                        
                        # Read data
                        for row in reader:
                            if len(row) > 1:  # At least frame number and one mouse column
                                try:
                                    frame_num = int(row[0])
                                    if 0 <= frame_num < self.frame_count:
                                        for col_idx, mouse_num in mouse_columns:
                                            if col_idx < len(row):
                                                mouse_idx = mouse_num - 1  # Convert to 0-based index
                                                zone = row[col_idx]
                                                if zone == 'A':
                                                    self.zone_arrays[mouse_idx][frame_num] = 1
                                                elif zone == 'B':
                                                    self.zone_arrays[mouse_idx][frame_num] = 2
                                except ValueError:
                                    continue
            except Exception as e:
                print(f"Error loading CSV file: {e}")
                # If CSV loading fails, initialize with default mouse count
                self.initialize_zone_arrays()
        else:
            # If no CSV file exists, initialize with default mouse count
            self.initialize_zone_arrays()
        
        # Update custom slider and annotation bar
        self.custom_slider.set_frame_count(self.frame_count)
        self.annotation_bar.set_frame_count(self.frame_count)
        
        # Reset labels and update visualization
        self.update_zone_counts()
        self.update_frame()
        
    def format_time(self, frame_number):
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        total_seconds = frame_number / fps
        minutes = int(total_seconds // 60)
        seconds = int(total_seconds % 60)
        return f"{minutes}:{seconds:02d}"
        
    def update_frame(self):
        if self.cap is not None:
            ret, frame = self.cap.read()
            if ret:
                # Update slider position without triggering the callback
                self.current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                self.custom_slider.set_current_frame(self.current_frame)
                
                # Update time display
                current_time = self.format_time(self.current_frame)
                total_time = self.format_time(self.frame_count)
                self.time_label.setText(f"{current_time} / {total_time}")
                
                # Handle annotation if mouse is pressed
                if self.mouse_pressed and self.current_frame < self.frame_count:
                    if self.delete_mode_btn.isChecked():
                        self.zone_arrays[self.current_mouse][self.current_frame - 1] = 0
                    elif self.current_zone == 'A':
                        self.zone_arrays[self.current_mouse][self.current_frame - 1] = 1
                    elif self.current_zone == 'B':
                        self.zone_arrays[self.current_mouse][self.current_frame - 1] = 2
                    self.annotation_bar.set_zone_array(self.zone_arrays[self.current_mouse])
                
                # Convert frame to QPixmap and display
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_frame.shape
                bytes_per_line = ch * w
                qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, 
                                QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(qt_image).scaled(
                    self.video_label.size(), Qt.KeepAspectRatio)
                
                # Draw current frame number and zone status
                painter = QPainter(pixmap)
                painter.setPen(QPen(Qt.black, 2))  # Change to black color and thinner line
                font = painter.font()
                font.setPointSize(20)  # Reduce font size
                painter.setFont(font)
                
                # Draw frame number at the top
                frame_text = f"Frame: {self.current_frame}"
                painter.drawText(20, 30, frame_text)  # Adjust y position
                
                # Draw zone status below frame number
                if self.current_frame < len(self.zone_arrays[self.current_mouse]):
                    if self.zone_arrays[self.current_mouse][self.current_frame - 1] == 1:
                        painter.setPen(QPen(Qt.red, 3))
                        painter.drawText(20, 60, "ZONE A")
                    elif self.zone_arrays[self.current_mouse][self.current_frame - 1] == 2:
                        painter.setPen(QPen(Qt.blue, 3))
                        painter.drawText(20, 60, "ZONE B")
                
                painter.end()
                self.video_label.setPixmap(pixmap)
            else:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                
    def update_visualization(self):
        if self.zone_arrays is None or self.frame_count == 0:
            return
            
        # Create a pixmap for the visualization bar
        width = self.custom_slider.width()
        height = self.custom_slider.height()
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.white)
        
        painter = QPainter(pixmap)
        
        # Calculate the width of each frame in the visualization
        frame_width = width / (self.frame_count - 1)  # Adjust for frame count
        
        # Draw the visualization
        for i in range(self.frame_count):
            x = int(i * frame_width)
            if self.zone_arrays[self.current_mouse][i] == 1:  # Zone A
                painter.fillRect(x, 0, int(frame_width) + 1, height, QColor(255, 0, 0))  # Red
            elif self.zone_arrays[self.current_mouse][i] == 2:  # Zone B
                painter.fillRect(x, 0, int(frame_width) + 1, height, QColor(0, 0, 255))  # Blue
        
        painter.end()
        self.custom_slider.update()
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_visualization()
        
    def speed_changed(self):
        speed_percent = self.speed_spinbox.value()
        self.playback_speed = speed_percent / 100.0
        if self.timer.isActive():
            self.timer.stop()
            self.timer.start(int(100 / self.playback_speed))
                
    def toggle_play(self):
        if self.timer.isActive():
            self.timer.stop()
            self.play_btn.setText("Play")
        else:
            self.timer.start(int(30 / self.playback_speed))
            self.play_btn.setText("Pause")
            
    def toggle_delete_mode(self):
        if self.delete_mode_btn.isChecked():
            self.delete_mode_btn.setStyleSheet("background-color: red;")
        else:
            self.delete_mode_btn.setStyleSheet("")
            
    def delete_all_labels(self):
        if self.zone_arrays is None:
            return
            
        reply = QMessageBox.question(self, 'Delete All Labels',
                                   'Are you sure you want to delete all labels?',
                                   QMessageBox.Yes | QMessageBox.No,
                                   QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            for mouse_idx in range(self.mouse_count):
                self.zone_arrays[mouse_idx].fill(0)
            self.update_zone_counts()
            self.update_visualization()
            self.save_results()
            
    def update_zone_counts(self):
        if self.zone_arrays is None:
            return
            
        zone_a_count = np.sum(self.zone_arrays[self.current_mouse] == 1)
        zone_b_count = np.sum(self.zone_arrays[self.current_mouse] == 2)
        total_count = zone_a_count + zone_b_count
        
        ratio = "N/A"
        if total_count > 0:
            ratio = f"{zone_a_count/(zone_a_count + zone_b_count):.2f}" if zone_b_count > 0 else "∞"
            
        analysis_text = f"Zone A Frames: {zone_a_count}\n"
        analysis_text += f"Zone B Frames: {zone_b_count}\n"
        analysis_text += f"A/B Ratio: {ratio}\n"
        analysis_text += f"Total Labeled Frames: {total_count}"
        
        self.analysis_text.setText(analysis_text)
        
    def mouse_press_event(self, event):
        if self.mouse_pressed == True:
            return
        
        self.mouse_pressed = True
        if self.delete_mode_btn.isChecked():
            self.current_zone = None
        else:
            if event.button() == Qt.LeftButton:
                self.current_zone = 'A'
            elif event.button() == Qt.RightButton:
                self.current_zone = 'B'
            
    def mouse_release_event(self, event):
        if event.button() in [Qt.LeftButton, Qt.RightButton]:
            self.mouse_pressed = False
            self.current_zone = None
            self.update_zone_counts()
            self.update_visualization()
            self.save_results()
            
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event):
        urls = event.mimeData().urls()
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.mpg']
        
        for url in urls:
            file_path = url.toLocalFile()
            if any(file_path.lower().endswith(ext) for ext in video_extensions):
                # Check if file already exists in the list
                if not any(self.file_list.item(i).text() == file_path for i in range(self.file_list.count())):
                    self.file_list.addItem(file_path)

    def file_list_drag_enter_event(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def file_list_drop_event(self, event):
        urls = event.mimeData().urls()
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv']
        
        for url in urls:
            file_path = url.toLocalFile()
            if any(file_path.lower().endswith(ext) for ext in video_extensions):
                # Check if file already exists in the list
                if not any(self.file_list.item(i).text() == file_path for i in range(self.file_list.count())):
                    self.file_list.addItem(file_path)

    def file_list_key_press_event(self, event):
        if event.key() in [Qt.Key_Delete, Qt.Key_Backspace]:
            # Get selected items
            selected_items = self.file_list.selectedItems()
            if selected_items:
                # Remove selected items
                for item in selected_items:
                    self.file_list.takeItem(self.file_list.row(item))
        else:
            QListWidget.keyPressEvent(self.file_list, event)

    def save_results(self):
        if self.zone_arrays is None or self.video_path is None:
            return
            
        # Check if there are any annotations
        if np.sum(self.zone_arrays[self.current_mouse] > 0) == 0:
            return
            
        # Create CSV filename in the same directory as the video
        video_dir = os.path.dirname(self.video_path)
        video_name = os.path.splitext(os.path.basename(self.video_path))[0]
        csv_path = os.path.join(video_dir, f"{video_name}.csv")
        
        # Prepare header
        header = ['Frame']
        for i in range(self.mouse_count):
            header.append(f'Mouse {i+1}')
            
        # Save results to CSV
        with open(csv_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(header)  # Header
            
            for frame_num in range(self.frame_count):
                row = [frame_num]
                for mouse_idx in range(self.mouse_count):
                    zone = self.zone_arrays[mouse_idx][frame_num]
                    zone_str = 'A' if zone == 1 else 'B' if zone == 2 else ''
                    row.append(zone_str)
                writer.writerow(row)
                
        print(f"Results saved to {csv_path}")
        
    def closeEvent(self, event):
        # Save results when closing the window
        self.save_results()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            if event.modifiers() & Qt.ControlModifier:
                # Move 10 frames backward
                new_frame = max(0, self.current_frame - 11)
            else:
                # Move 1 frame backward
                new_frame = max(0, self.current_frame - 2)
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, new_frame)
            self.update_frame()
        elif event.key() == Qt.Key_Right:
            if event.modifiers() & Qt.ControlModifier:
                # Move 10 frames forward
                new_frame = min(self.frame_count - 1, self.current_frame + 9)
            else:
                # Move 1 frame forward
                new_frame = min(self.frame_count - 1, self.current_frame)
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, new_frame)
            self.update_frame()
        elif event.key() == Qt.Key_D:
            self.delete_mode_btn.setChecked(not self.delete_mode_btn.isChecked())
            self.toggle_delete_mode()

    def mouse_count_changed(self, count):
        new_mouse_count = int(count)
        old_mouse_count = self.mouse_count
        self.mouse_count = new_mouse_count
        
        # Save existing zone arrays if they exist
        old_zone_arrays = None
        if self.zone_arrays is not None:
            old_zone_arrays = self.zone_arrays.copy()
            
        # Update mouse selection UI
        self.update_mouse_selection()
        
        # Initialize new zone arrays
        if self.frame_count > 0:
            self.zone_arrays = [np.zeros(self.frame_count + 1, dtype=np.int8) for _ in range(self.mouse_count)]
            
            # Copy over existing data if we had previous arrays
            if old_zone_arrays is not None:
                # Copy data for mice that existed in both old and new counts
                copy_count = min(old_mouse_count, new_mouse_count)
                for i in range(copy_count):
                    if i < len(old_zone_arrays) and i < len(self.zone_arrays):
                        self.zone_arrays[i] = old_zone_arrays[i].copy()
            
            # Update the annotation bar with current mouse's data
            if self.current_mouse < len(self.zone_arrays):
                self.annotation_bar.set_zone_array(self.zone_arrays[self.current_mouse])
            
    def update_mouse_selection(self):
        self.mouse_select_combo.clear()
        self.mouse_select_combo.addItems([f"Mouse {i+1}" for i in range(self.mouse_count)])
        
    def mouse_selection_changed(self, index):
        self.current_mouse = index
        if self.zone_arrays is not None:
            self.annotation_bar.set_zone_array(self.zone_arrays[self.current_mouse])
            self.update_zone_counts()
            
    def initialize_zone_arrays(self):
        if self.frame_count > 0:
            self.zone_arrays = [np.zeros(self.frame_count + 1, dtype=np.int8) for _ in range(self.mouse_count)]
            self.annotation_bar.set_zone_array(self.zone_arrays[self.current_mouse])
            
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MouseBehaviorAnalyzer()
    window.show()
    sys.exit(app.exec_()) 