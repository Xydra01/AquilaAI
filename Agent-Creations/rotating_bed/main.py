import matplotlib.pyplot as plt
import numpy as np
import math


def create_rotating_bed_animation():
    """Create an animation of a bed rotating smoothly."""

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_xlim(-3, 5)
    ax.set_ylim(-2, 2)
    ax.grid(True, alpha=0.3)

    rotation_speed_deg_per_frame = 360.0 / 60.0

    def update(frame):
        """Update the bed position for each frame."""
        ax.clear()

        rotation_angle_rad = frame * math.radians(rotation_speed_deg_per_frame)
        bed_center_x, bed_center_y = 0.5, -0.2

        # Helper function to rotate a point around bed center
        def rotate_point(px, py):
            dx = px - bed_center_x
            dy = py - bed_center_y
            rx = bed_center_x + dx * math.cos(rotation_angle_rad) - dy * math.sin(rotation_angle_rad)
            ry = bed_center_y + dx * math.sin(rotation_angle_rad) + dy * math.cos(rotation_angle_rad)
            return (rx, ry)

        # Create mattress rectangle
        half_w, half_h = 2.5, 0.6
        rect_points = [
            (bed_center_x - half_w / 2, bed_center_y - half_h / 2),
            (bed_center_x + half_w / 2, bed_center_y - half_h / 2),
            (bed_center_x + half_w / 2, bed_center_y + half_h / 2),
            (bed_center_x - half_w / 2, bed_center_y + half_h / 2)
        ]

        rotated_rect = []
        for px, py in rect_points:
            rx, ry = rotate_point(px, py)
            rotated_rect.append((rx, ry))

        mattress = plt.Polygon(rotated_rect, closed=True, facecolor="#D2691E",
                               edgecolor="#8B4513", linewidth=2, alpha=0.9)
        ax.add_patch(mattress)

        # Create headboard (fixed at top of mattress in local coordinates)
        headboard_points = [(-1.2, -0.7), (1.2, -0.7), (1.5, -1.0), (-1.5, -1.0)]

        rotated_headboard = []
        for px, py in headboard_points:
            rx, ry = rotate_point(px, py)
            rotated_headboard.append((rx, ry))

        headboard = plt.Polygon(rotated_headboard, closed=True, facecolor="#A0522D",
                                edgecolor="#8B4513", linewidth=2, alpha=0.9)
        ax.add_patch(headboard)

        # Create pillows (3 pillows at head of bed)
        for i in range(3):
            p_x = -0.8 + i * 0.6
            p_y = 0.4
            theta = np.linspace(0, 2 * np.pi, 100)
            pillow_points = []
            for t in theta:
                px_pillow = p_x + math.cos(t)
                py_pillow = p_y + math.sin(t)
                rx_pillow, ry_pillow = rotate_point(px_pillow, py_pillow)
                pillow_points.append((rx_pillow, ry_pillow))

            pillow = plt.Polygon(pillow_points, closed=True, facecolor="#F5DEB3",
                                 edgecolor="#D2691E", linewidth=1, alpha=0.8)
            ax.add_patch(pillow)

        # Create bed frame (simple rectangular outline below mattress)
        frame_points = [(-2.5, -1.5), (2.5, -1.5), (2.5, 0.6), (-2.5, 0.6)]

        rotated_frame = []
        for px, py in frame_points:
            rx, ry = rotate_point(px, py)
            rotated_frame.append((rx, ry))

        frame = plt.Polygon(rotated_frame, closed=True, facecolor="#8B4513",
                            edgecolor="#654321", linewidth=3, alpha=0.7)
        ax.add_patch(frame)

        # Update angle display
        rotation_degrees = (frame * 360) % 360
        info_text = f"Rotation Angle: {rotation_degrees:.1f}°"
        ax.text(0.5, -1.8, info_text, ha="center", va="center",
                transform=ax.transAxes, fontsize=12, color="#4A4A4A")

        plt.axis("off")  # disable axis

    # Create and run the animation
    _ = plt.FuncAnimation(fig, update, frames=60, interval=17, blit=False)


if __name__ == "__main__":
    create_rotating_bed_animation()