Requirements

Hardware:
  Raspberry Pi (any model with GPIO pins)
  Servo motor for steering
  DC motor with motor controller (e.g., DROK)
  Xbox controller (wired or wireless with adapter)
  Raspberry Pi Camera module or USB webcam

Software / Libraries:
  Python 3.x
  OpenCV (cv2)
  RPi.GPIO
  ApproxEng input library (approxeng.input)
  time, datetime (Python standard libraries)

Wiring
  Servo Motor: Connect the control pin to GPIO 17.
  DC Motor: Connect the motor controller pins as follows:
    IN1 → GPIO 24
    IN2 → GPIO 25
    ENA → GPIO 23


Usage
  1.Connect your Xbox controller to the Raspberry Pi.
  2.Connect the motors and camera to the Raspberry Pi.
  3.Run the script
  4.Control the robot with the Xbox controller:
    Left joystick: Steering (left/right)
    D-Pad Up: Move forward
    D-Pad Down: Move backward
    Y button (l1): Stop motor
    A button (cross): Stop script and cleanup GPIO

The script logs each input with timestamp and saves images to the image directory.
