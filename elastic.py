"""Room where the stops are: a diffusion cartogram (Gastner & Newman 2004).

Stop density on a fine grid is let to diffuse like heat until it's even; every point moves with the flow
(velocity = -grad(density) / density). Dense places (the centre, but just as much Silivri or Büyükçekmece) spread
out, empty forest and sea give way. The flow is smooth, so the map can't fold: neighbours stay neighbours and the
order of places along a line is kept. A regular mesh is carried along; any point is then placed by interpolating
inside its mesh cell.
"""
import numpy as np


class Elastic:
    def __init__(self, points, box, cell=0.5, base=0.3, blur=2.0, pad=0.5, land=None):
        """points: (x, y) in km of every stop; box (x0, y0, x1, y1) in km; cell km per grid cell; base: density of
        empty land as a share of the mean density where there are stops (lower: forest shrinks more). land: rings
        of (x, y) km; the sea outside them keeps the land's average density, so it keeps its size and the coast
        its shape."""
        x0, y0, x1, y1 = box
        self.cell = cell
        nx, ny = int(np.ceil((x1 - x0) / cell)), int(np.ceil((y1 - y0) / cell))
        px, py = int(nx * pad), int(ny * pad)            # room around, so the flow isn't boxed in
        NX, NY = _even(nx + 2 * px), _even(ny + 2 * py)
        self.ox, self.oy = x0 - px * cell, y0 - py * cell
        self.NX, self.NY = NX, NY
        pts = np.asarray(points, float)
        ix = np.clip(((pts[:, 0] - self.ox) / cell).astype(int), 0, NX - 1)
        iy = np.clip(((pts[:, 1] - self.oy) / cell).astype(int), 0, NY - 1)
        dens = np.zeros((NY, NX))
        np.add.at(dens, (iy, ix), 1.0)
        dens = _blur(dens, blur)
        mean = dens[dens > dens.max() * 1e-3].mean()
        rho0 = dens + base * mean
        if land:
            from PIL import Image, ImageDraw
            img = Image.new("1", (NX, NY), 0)
            draw = ImageDraw.Draw(img)
            for ring in land:
                draw.polygon([((x - self.ox) / cell, (y - self.oy) / cell) for x, y in ring], fill=1)
            is_land = np.array(img, dtype=bool)
            rho0 = np.where(is_land, rho0, rho0[is_land].mean())
        rho_hat = np.fft.fft2(rho0)
        kx = 2 * np.pi * np.fft.fftfreq(NX)[None, :]
        ky = 2 * np.pi * np.fft.fftfreq(NY)[:, None]
        k2 = kx ** 2 + ky ** 2

        # the mesh carried by the flow: every grid vertex, in grid units
        gy, gx = np.mgrid[0:NY + 1, 0:NX + 1].astype(float)
        P = np.stack([gx.ravel(), gy.ravel()], axis=1)
        t, steps = 0.0, 0
        t_end = 4.0 * (max(NX, NY) / np.pi) ** 2        # long enough for the density to be even
        while t < t_end and steps < 4000:
            decay = np.exp(-k2 * t)
            rho = np.real(np.fft.ifft2(rho_hat * decay))
            gxr = np.real(np.fft.ifft2(rho_hat * decay * 1j * kx))
            gyr = np.real(np.fft.ifft2(rho_hat * decay * 1j * ky))
            vx, vy = -gxr / rho, -gyr / rho
            vmax = max(np.abs(vx).max(), np.abs(vy).max(), 1e-12)
            dt = min(0.2 / vmax, t_end - t, max(t, 1.0))  # move at most a fifth of a cell a step
            P += dt * np.stack([_interp(vx, P), _interp(vy, P)], axis=1)
            t += dt; steps += 1
            if vmax * dt < 1e-4 and t > 50:
                break
        self.steps = steps
        self.V = (P.reshape(NY + 1, NX + 1, 2) * cell) + np.array([self.ox, self.oy])
        c = self.V
        cross = ((c[:-1, 1:, 0] - c[:-1, :-1, 0]) * (c[1:, :-1, 1] - c[:-1, :-1, 1])
                 - (c[:-1, 1:, 1] - c[:-1, :-1, 1]) * (c[1:, :-1, 0] - c[:-1, :-1, 0]))
        self.folded = int((cross <= 0).sum())

    def __call__(self, x, y):
        fx, fy = (x - self.ox) / self.cell, (y - self.oy) / self.cell
        j = min(max(int(np.floor(fx)), 0), self.NX - 1)
        i = min(max(int(np.floor(fy)), 0), self.NY - 1)
        tx, ty = fx - j, fy - i
        V = self.V
        p = (V[i, j] * (1 - tx) * (1 - ty) + V[i, j + 1] * tx * (1 - ty)
             + V[i + 1, j] * (1 - tx) * ty + V[i + 1, j + 1] * tx * ty)
        return float(p[0]), float(p[1])


def _even(n):
    return n + (n % 2)


def _interp(field, P):
    """Bilinear value of a periodic grid field at points P (grid units, x then y)."""
    NY, NX = field.shape
    x, y = P[:, 0], P[:, 1]
    j0 = np.floor(x).astype(int); i0 = np.floor(y).astype(int)
    tx, ty = x - j0, y - i0
    j0 %= NX; i0 %= NY
    j1, i1 = (j0 + 1) % NX, (i0 + 1) % NY
    return (field[i0, j0] * (1 - tx) * (1 - ty) + field[i0, j1] * tx * (1 - ty)
            + field[i1, j0] * (1 - tx) * ty + field[i1, j1] * tx * ty)


def _blur(a, sigma):
    if sigma <= 0:
        return a
    r = int(3 * sigma)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    a = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 0, a)
    return np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 1, a)
