#version 450
layout(location = 0) out vec4 FragColor;
uniform float u_time;
uniform vec2 u_center;
uniform vec3 u_center_color;
uniform vec3 u_edge_color;

void main() {
    vec2 offset = gl_FragCoord.xy - u_center;
    float r = length(offset);
    float theta = atan(offset.y, offset.x);
    theta += u_time * 2.0;
    vec2 rotated = vec2(r * cos(theta), r * sin(theta));
    vec2 final_uv = rotated + u_center;
    
    float dist = length(final_uv - u_center);
    float alpha = smoothstep(0.5, 1.0, dist);
    
    // Color gradient based on distance
    float normalized_dist = dist / 1.0;
    vec3 color = mix(u_center_color, u_edge_color, normalized_dist);
    
    FragColor = vec4(color, alpha);
}