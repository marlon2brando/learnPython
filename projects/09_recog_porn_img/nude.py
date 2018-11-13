import sys
import os
import _io
from collections import namedtuple
from PIL import Image


class Nude(object):

    Skin = namedtuple("Skin",'id skin region x y')

    def __init__(self,path_or_image):
        # 如果是Image类，直接赋值
        if isinstance(path_or_image,Image.Image):
            self.image = path_or_image
        elif isinstance(path_or_image,str):
            self.image = Image.open(path_or_image)


        # 获得图片的所有颜色通道
        bands = self.image.getbands()
        # 判断是否是单通道图片（也即灰度图片），是则将灰度图片转换成 RGB图
        if len(bands) == 1:
            # 新建相同大小的RGB图像
            new_img = Image.new("RGB",self.image.size)
            # 拷贝灰度图 self.image到RGB图的new_image.paste
            new_img.paste(self.image)
            f = self.image.filename
            # 替换self.image
            self.image = new_img
            self.image.filename = f

        # 存储对应图像的所有像素的全部Skin对象
        self.skin_map = []
        # 检测到的皮肤区域
        self.detected_regions = []
        # 待合并区域
        self.merge_regions = []
        # 确认为皮肤区域的ski对象集合
        self.skin_regions = []
        # 最近合并的两个皮肤区域的区域号 初始化为-1
        self.last_from,self.last_to = -1,-1
        # 结果
        self.result = None
        # 处理得到的信息
        self.message = None
        # 图像宽高
        print(self.image.size)
        self.width,self.height = self.image.size
        # 图片的像素数量
        self.total_pixels = self.width * self.height


    # 图片缩小
    def resize(self,maxwidth=1000,masheight=1000):
        '''
        基于最大宽高按比例重设图片大小，
        注意：这可能影响检测算法的结果

        如果没有变化返回 0
        原宽度大于 maxwidth 返回 1
        原高度大于 maxheight 返回 2
        原宽高大于 maxwidth, maxheight 返回 3

        maxwidth - 图片最大宽度
        maxheight - 图片最大高度
        传递参数时都可以设置为 False 来忽略
        '''
        ret = 0
        if maxwidth:
            if self.width > maxwidth:
                wpercent = (maxwidth/self.width)
                hsize = int(self.height * wpercent)
                fname = self.image.filename

                # Image.LANCZOS 重采样滤波器，用于抗锯齿
                self.image = self.image.resize((maxwidth,hsize),Image.LANCZOS)
                self.image.filename = fname
                self.width,self.height = self.image.size
                self.total_pixels = self.width * self.height
                ret += 1
        if maxheight:
            if self.height > maxheight:
                hpercent = (maxheight / float(self.height))
                wsize = int((float(self.width) * float(hpercent)))
                fname = self.image.filename

                self.image = self.image.resize((wsize,maxheight),Image.LANCZOS)
                self.image.filename = filename
                self.width ,self.height = self.image.size
                self.total_pixels = self.width * self.height
                ret += 2
        return ret


    # 分析函数
    def parse(self):
        # 如果已有结果，直接返回本对象
        if self.result is not None:
            return self
        #获取图片的所有像素数据
        pixels = self.image.load()

        for y in range(self.height):
            for x in range(self.width):
                r = pixels[x,y][0] #red
                g = pixels[x,y][1] #green
                b = pixels[x,y][2] #blue

                # 判断当前像素是否为肤色像素
                isSkin = True if self._classify_skin(r,g,b) else False

                # 给每个像素分配 id。（1，2，3...heght*width）
                _id = x+y * self.width + 1
                # 为每个像素创建对应的SKin对象，并添加到 skin_map中去
                self.skin_map.append(self.Skin(_id,isSkin,None,x,y))

                # 如果不是皮肤像素，则跳出循环
                if not isSkin:
                    continue

                check_indexes = [_id - 2, #左边像素
                                 _id - self.width - 2,# 左上角像素
                                 _id - self.width - 1, # 上方像素
                                 _id - self.width #右上角像素
                                ]
                # 用来记录相邻像素所在区域号，初始化为-1
                region = -1
                for index in check_indexes:
                    try:
                        self.skin_map[index]
                    except IndexError:
                        break

                    if self.skin_map[index].skin:
                        # 若相邻像素月当前像素的region 均为有效值，且二者不同，且尚未添加的合并任务
                        if(self.skin_map[index].region != None and region != None and region != -1 and self.skin_map[index].region != region and self.last_from != region and self.last_to != self.skin_map[index].region):
                            self._add_merge(region,self.skin_map[index].region)
                        region = self.skin_map[index].region
                #遍历完所有相邻元素后，region任然= -1,说明所有相邻原色都不是肤色像素
                if region == -1:
                    # 更改属性为新的区域号，注意元祖是不可变类型，不能直接更改属性，region号是 一发现的region list的长度
                    _skin = self.skin_map[_id-1]._replace(region=len(self.detected_regions))
                    self.skin_map[_id - 1] = _skin
                    # 将次肤色像素所在区域创建为新区域
                    self.detected_regions.append([self.skin_map[_id-1]])
                elif region != None:
                    _skin = self.skin_map[_id-1]._replace(region=region)
                    self.skin_map[_id-1] = _skin

                    self.detected_regions[region].append(self.skin_map[_id-1])

        # 完成所有区域的合并任务，并整理合并的区域存储到 self.skin_regions
        self._merge(self.detected_regions,self.merge_regions)
        # 分析皮肤区域，得到判定结果
        self._analyse_regions()
        return self


# 基于像素的肤色检测技术
    def _classify_skin(self,r,g,b):
        # 根据 RGB值判断
        rgb_classifer = r > 95 and \
                        g > 40 and \
                        g < 100 and \
                        b > 20 and \
                        max([r,g,b]) - min([r,g,b]) > 15 and \
                        abs(r-g) > 15 and \
                        r > g and \
                        r < b
        # 根据处理后的RGB值判定
        nr,ng,nb = self._to_normalized(r,g,b)
        norm_rgb_classifier = nr/ ng > 1.185 \
                        and   float(r*b)/((r+g+b)**2) > 0.107 \
                        and   float(r * g) / ((r + g + b) ** 2) > 0.112


        # HSV颜色模式下的判定
        h ,s, v = self._to_hsv(r,g,b)
        hsv_classifier = h > 0 and h < 35 and s > 0.23 and s < 0.68

        # YCbCr 颜色模式下的判定
        y, cb, cr = self._to_ycbcr(r, g,  b)
        ycbcr_classifier = 97.5 <= cb <= 142.5 and 134 <= cr <= 176

        # 效果不好 
        # return rgb_classifer or norm_rgb_classifier or hsv_classifier or ycbcr_classifier
        return ycbcr_classifier


    def _add_merge(self,_from,_to):
        # 给类属性赋值
        self.last_from = _from
        self.last_to = _to

        from_index = -1
        to_index = -1

        for index,region in enumerate(self.merge_regions):
            for r_index in region:
                if r_index == _from:
                    from_index = index
                if r_index == _to:
                    to_index = index

        if from_index != -1 and to_index != -1:
            if from_index != to_index:
                self.merge_regions[from_index].extend(self.merge_regions[to_index])
                del(self.merge_regions[to_index])
            return

        if from_index == -1 and to_index != -1:
            self.merge_regions.append([_from,_to])
            return

        if from_index != -1 and to_index == -1:
            self.merge_regions[from_index].append(_to)
            return

        if from_index == -1 and to_index != -1:
            self.merge_regions[to_index].append(_from)
            return


    def _merge(self,detected_regions,merge_regions):
        new_detected_regions = []

        for index,region in enumerate(merge_regions):
            try:
                new_detected_regions[index]
            except IndexError:
                new_detected_regions.append([])

            for r_index in region:
                new_detected_regions[index].extend(detected_regions[r_index])
                detected_regions[r_index] = []

        for region in detected_regions:
            if len(region) > 0:
                new_detected_regions.append(region)

        self._clear_regions(new_detected_regions)


    def _clear_regions(self,detected_regions):
        for region in detected_regions:
            if len(region) > 30:
                self.skin_regions.append(region)

    def _analyse_regions(self):
        if len(self.skin_regions) < 3:
            self.message = "Less than 3 skin regions ({_skin_regions_size})".format(_skin_regions_size = len(self.skin_regions))
            self.result = False
            return self.result

        self.skin_regions = sorted(self.skin_regions,key=lambda s:len(s),reverse = True)

        total_skin = float(sum( [len(skin_region) for skin_region in self.skin_regions]))

        if total_skin / self.total_pixels * 100 < 15:
            self.message = "Total skin percentage lower than 15 ({:.2f}".format(total_skin/self.total_pixels*100)
            self.result = False
            return self.result

             # 如果最大皮肤区域小于总皮肤面积的 45%，不是色情图片
        if len(self.skin_regions[0]) / total_skin * 100 < 45:
            self.message = "The biggest region contains less than 45 ({:.2f})".format(len(self.skin_regions[0]) / total_skin * 100)
            self.result = False
            return self.result

        # 皮肤区域数量超过 60个，不是色情图片
        if len(self.skin_regions) > 60:
            self.message = "More than 60 skin regions ({})".format(len(self.skin_regions))
            self.result = False
            return self.result

        # 其它情况为色情图片
        self.message = "Nude!!"
        self.result = True
        return self.result


    def inspect(self):
        _image = '{} {} {}x{}'.format(self.image.filename,self.image.format,self.width,self.height)
        return "{_image}:result = {_result} message='{_message}'".format(_image=_image,_result=self.result,_message=self.message)


    def showSkinRegions(self):
        if self.result is None:
            return

        skinIdSet = set()
        simage = self.image
        simageData = simage.load()

        for sr in self.skin_regions:
            for pixel in sr:
                skinIdSet.add(pixel.id)

        for pixel in self.skin_map:
            if pixel.id not in skinIdSet:
                simageData[pixel.x,pixel.y] = 0,0,0
            else:
                simageData[pixel.x,pixel.y] = 255,255,255

        filepath = os.path.abspath(self.image.filename)
        filedir = os.path.dirname(filepath) + '/'
        fileFullName = os.path.basename(filepath)
        filename,fileExtName = os.path.splitext(fileFullName)

        simage.save('{}{}_{}{}'.format(filedir,filename,'Nude' if self.result else 'Normal',fileExtName))






    def _to_normalized(self, r, g, b):
        if r == 0:
            r = 0.0001
        if g == 0:
            g = 0.0001
        if b == 0:
            b = 0.0001
        _sum = float(r + g + b)
        return [r / _sum, g / _sum, b / _sum]





    def _to_ycbcr(self, r, g, b):
        # 公式来源：
        # http://stackoverflow.com/questions/19459831/rgb-to-ycbcr-conversion-problems
        y = .299*r + .587*g + .114*b
        cb = 128 - 0.168736*r - 0.331364*g + 0.5*b
        cr = 128 + 0.5*r - 0.418688*g - 0.081312*b
        return y, cb, cr

    def _to_hsv(self, r, g, b):
        h = 0
        _sum = float(r + g + b)
        _max = float(max([r, g, b]))
        _min = float(min([r, g, b]))
        diff = float(_max - _min)
        if _sum == 0:
            _sum = 0.0001

        if _max == r:
            if diff == 0:
                h = sys.maxsize
            else:
                h = (g - b) / diff
        elif _max == g:
            h = 2 + ((g - r) / diff)
        else:
            h = 4 + ((r - g) / diff)

        h *= 60
        if h < 0:
            h += 360

        return [h, 1.0 - (3.0 * (_min / _sum)), (1.0 / 3.0) * _max]





if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description = 'Detect nudity in images')
    parser.add_argument('files',metavar='image',nargs='+',help='Images you wish to test')
    parser.add_argument('-r','--resize',action='store_true',help='Reduce image size to increse speed of scanning')
    parser.add_argument('-v','--visualization',action='store_true',help='Generating areas of skin image')

    args = parser.parse_args()

    for fname in args.files:
        if os.path.isfile(fname):
            n = Nude(fname)
            if args.resize:
                n.resize(maxheight=800,maxwidth=600)
            n.parse()
            if args.visualization:
                n.showSkinRegions()
            print(n.result,n.inspect())
        else:
            print(fnamem,'is not a file')










