#version 440
// (1.7.7, la persona eligio «Nebulosa esmeralda») El fondo del programa: gas cosmico con ruido fractal deformado
// (domain warping), un brillo dorado en lo mas denso y estrellas que titilan. Corre en la tarjeta de video (Qt Quick
// ShaderEffect): la ventana de widgets NO se repinta por esto. Se compila a nebulosa.frag.qsb con
//   pyside6-qsb --glsl "100es,120,150" --hlsl 50 --msl 12 -o nebulosa.frag.qsb nebulosa.frag
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float t;        // segundos
    float aspecto;  // ancho / alto
    float brillo;   // 0..1: cuanto se ve la nebulosa (las tarjetas deben leerse encima)
};

float h(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float n(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(h(i), h(i + vec2(1.0, 0.0)), f.x), mix(h(i + vec2(0.0, 1.0)), h(i + 1.0), f.x), f.y);
}
float fbm(vec2 p) {
    float v = 0.0, a = 0.5;
    for (int i = 0; i < 6; i++) { v += a * n(p); p = p * 2.03 + vec2(1.7, 9.2); a *= 0.5; }
    return v;
}
float estrellas(vec2 u, float d) {
    vec2 g = fract(u * d) - 0.5;
    float s = h(floor(u * d));
    return step(0.990, s) * smoothstep(0.22, 0.0, length(g)) * (0.55 + 0.45 * sin(t * 2.0 + s * 600.0));
}

void main() {
    vec2 u = qt_TexCoord0;
    vec2 p = vec2(u.x * aspecto, 1.0 - u.y);
    vec2 q = vec2(fbm(p * 1.6 + t * 0.015), fbm(p * 1.6 + vec2(5.2, 1.3)));
    float f = fbm(p * 1.6 + 3.5 * q + vec2(t * 0.02, -t * 0.01));
    // (cerca del cielo de antes: esmeralda azulado, no oliva; el dorado solo en el centro mas denso)
    vec3 c = mix(vec3(0.004, 0.012, 0.020), vec3(0.015, 0.22, 0.23), smoothstep(0.35, 0.95, f) * brillo);
    c = mix(c, vec3(0.05, 0.42, 0.42), smoothstep(0.66, 1.0, f) * 0.55 * brillo);
    c += vec3(0.95, 0.80, 0.50) * pow(f, 9.0) * 0.9 * brillo;
    c += vec3(0.85, 0.95, 1.0) * (estrellas(p, 300.0) * 1.1 + estrellas(p + 3.0, 140.0) * 0.8 + estrellas(p + 7.0, 60.0) * 0.6);
    vec2 v = u * (1.0 - u);
    c *= pow(v.x * v.y * 15.0, 0.25);                // vineta
    fragColor = vec4(c, 1.0) * qt_Opacity;
}
